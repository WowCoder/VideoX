"""审计 026+ 生产迁移并安全绑定现有用户的手机号身份。

这个脚本用于发布窗口和隔离演练：

* ``audit`` 始终只读，保存脱敏 JSON 报告；
* ``bind`` 默认在事务中演练后回滚，只有显式 ``--apply`` 和确认串才提交；
* 手机号从权限受限的 JSON 文件读取，不作为命令行参数或日志输出；
* 业务用户和关键实体的 ID 摘要必须与迁移前基线一致。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.user import User, UserIdentity  # noqa: E402
from app.services.auth_identities import (  # noqa: E402
    EMAIL_PROVIDER,
    PHONE_PROVIDER,
    normalize_email_identity,
    normalize_phone_identity,
)


APPLY_CONFIRMATION = "BIND_PRODUCTION_PHONE_IDENTITIES"
# VideoX guards both historical and current phone placeholder addresses before binding.
PHONE_PLACEHOLDER_EMAIL_PATTERN = r"^[0-9]{11}@(openvma|videox)\.cn$"
ENTITY_SPECS: dict[str, str | None] = {
    "users": None,
    "projects": "owner_id",
    "assets": "owner_id",
    "jobs": "owner_id",
    "inspiration_tasks": "owner_id",
    "notifications": "user_id",
    "orders": "user_id",
    "usages": "user_id",
    "subscriptions": "user_id",
    "invoices": "user_id",
    "voice_profiles": "owner_id",
    "project_asset_links": "linked_by",
    "project_revisions": "created_by",
}


class ReleaseIdentityError(RuntimeError):
    pass


def _sha256_lines(values: list[str]) -> str:
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mask_identifier(provider: str, identifier: str) -> str:
    if provider == PHONE_PROVIDER:
        digits = identifier.removeprefix("+86")
        if len(digits) == 11:
            return f"+86{digits[:3]}****{digits[-4:]}"
        return "+86***"
    if provider == EMAIL_PROVIDER and "@" in identifier:
        local, domain = identifier.split("@", 1)
        return f"{local[:1]}***@{domain}"
    return "***"


def _load_mapping(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ReleaseIdentityError(f"手机号映射文件不存在：{path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ReleaseIdentityError("手机号映射文件权限必须为 600 或更严格")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseIdentityError("手机号映射文件不是合法 JSON") from error
    bindings = payload.get("bindings") if isinstance(payload, dict) else None
    if not isinstance(bindings, list) or not bindings:
        raise ReleaseIdentityError("手机号映射必须包含非空 bindings 数组")

    result: dict[str, str] = {}
    phones: set[str] = set()
    for item in bindings:
        if not isinstance(item, dict):
            raise ReleaseIdentityError("bindings 中每一项必须是对象")
        user_id = str(item.get("user_id") or "").strip()
        if not user_id or user_id in result:
            raise ReleaseIdentityError("手机号映射包含空用户 ID 或重复用户")
        try:
            phone = normalize_phone_identity(str(item.get("phone") or ""))
        except ValueError as error:
            raise ReleaseIdentityError(f"用户 {user_id} 的手机号格式无效") from error
        if phone in phones:
            raise ReleaseIdentityError("手机号映射中存在重复手机号")
        result[user_id] = phone
        phones.add(phone)
    return result


async def _table_exists(session, table_name: str) -> bool:
    value = await session.scalar(
        text("SELECT to_regclass(:qualified_name) IS NOT NULL"),
        {"qualified_name": f"public.{table_name}"},
    )
    return bool(value)


async def _column_exists(session, table_name: str, column_name: str) -> bool:
    value = await session.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(value)


async def _alembic_version(session) -> str | None:
    if not await _table_exists(session, "alembic_version"):
        return None
    value = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return str(value) if value else None


async def _entity_snapshot(session, table_name: str, owner_column: str | None) -> dict[str, Any]:
    if not await _table_exists(session, table_name):
        return {"exists": False, "count": 0, "id_sha256": _sha256_lines([]), "ownership_sha256": _sha256_lines([])}
    if not table_name.replace("_", "a").isalnum():
        raise ReleaseIdentityError(f"非法表名：{table_name}")
    rows = (await session.execute(text(f"SELECT id FROM {table_name} ORDER BY id"))).scalars().all()
    identifiers = [str(value) for value in rows if value is not None]
    ownership: list[str] = []
    if owner_column:
        if not owner_column.replace("_", "a").isalnum():
            raise ReleaseIdentityError(f"非法所有者列：{owner_column}")
        owner_rows = (
            await session.execute(
                text(f"SELECT id, {owner_column} FROM {table_name} ORDER BY id")
            )
        ).all()
        ownership = [f"{row[0]}|{row[1] or ''}" for row in owner_rows]
    return {
        "exists": True,
        "count": len(identifiers),
        "id_sha256": _sha256_lines(identifiers),
        "ownership_sha256": _sha256_lines(ownership),
    }


async def _identity_snapshot(session) -> dict[str, Any]:
    if not await _table_exists(session, "user_identities"):
        return {
            "exists": False,
            "count": 0,
            "provider_counts": {},
            "provider_user_counts": {},
            "rows": [],
            "email_mismatches": 0,
            "duplicate_provider_identifiers": 0,
        }
    rows = (
        await session.execute(
            text(
                """
                SELECT i.user_id, i.provider, i.identifier,
                       CASE
                           WHEN i.provider = 'email'
                           THEN i.password_hash IS NOT DISTINCT FROM u.password_hash
                           ELSE true
                       END AS password_matches
                FROM user_identities i
                JOIN users u ON u.id = i.user_id
                ORDER BY i.user_id, i.provider, i.identifier
                """
            )
        )
    ).all()
    provider_counts: dict[str, int] = {}
    provider_users: dict[str, set[str]] = {}
    report_rows = []
    for user_id, provider, identifier, password_matches in rows:
        provider_counts[str(provider)] = provider_counts.get(str(provider), 0) + 1
        provider_users.setdefault(str(provider), set()).add(str(user_id))
        report_rows.append(
            {
                "user_id": str(user_id),
                "provider": str(provider),
                "identifier_masked": _mask_identifier(str(provider), str(identifier)),
                "identifier_sha256": hashlib.sha256(str(identifier).encode("utf-8")).hexdigest(),
                "password_matches_user": bool(password_matches),
            }
        )
    email_mismatches = int(
        await session.scalar(
            text(
                """
                SELECT count(*) FROM user_identities i
                JOIN users u ON u.id = i.user_id
                WHERE i.provider = 'email'
                  AND (
                    i.identifier <> lower(u.email)
                    OR i.password_hash IS DISTINCT FROM u.password_hash
                  )
                """
            )
        )
        or 0
    )
    duplicates = int(
        await session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT provider, identifier
                    FROM user_identities
                    GROUP BY provider, identifier
                    HAVING count(*) > 1
                ) duplicated
                """
            )
        )
        or 0
    )
    return {
        "exists": True,
        "count": len(rows),
        "provider_counts": provider_counts,
        "provider_user_counts": {
            provider: len(user_ids) for provider, user_ids in provider_users.items()
        },
        "rows": report_rows,
        "email_mismatches": email_mismatches,
        "duplicate_provider_identifiers": duplicates,
    }


async def _snapshot(session) -> dict[str, Any]:
    entities = {
        table_name: await _entity_snapshot(session, table_name, owner_column)
        for table_name, owner_column in ENTITY_SPECS.items()
    }
    user_rows = (
        await session.execute(select(User.id, User.email).order_by(User.id))
    ).all()
    users = [
        {
            "id": str(user_id),
            "email_masked": _mask_identifier(EMAIL_PROVIDER, str(email)),
            "email_sha256": hashlib.sha256(
                normalize_email_identity(str(email)).encode("utf-8")
            ).hexdigest(),
        }
        for user_id, email in user_rows
    ]
    snapshot_duplicates = 0
    if await _table_exists(session, "inspiration_source_snapshots"):
        snapshot_duplicates = int(
            await session.scalar(
                text(
                    """
                    SELECT count(*) FROM (
                        SELECT source_id, run_id
                        FROM inspiration_source_snapshots
                        GROUP BY source_id, run_id
                        HAVING count(*) > 1
                    ) duplicated
                    """
                )
            )
            or 0
        )
    legacy_phone_users = int(
        await session.scalar(
            text("SELECT count(*) FROM users WHERE email ~ :phone_placeholder_pattern"),
            {"phone_placeholder_pattern": PHONE_PLACEHOLDER_EMAIL_PATTERN},
        )
        or 0
    )
    casefold_duplicates = int(
        await session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT lower(email) FROM users
                    GROUP BY lower(email) HAVING count(*) > 1
                ) duplicated
                """
            )
        )
        or 0
    )
    columns_029 = {
        "inspiration_tasks.discovery_config": await _column_exists(session, "inspiration_tasks", "discovery_config"),
        "inspiration_sources.last_status": await _column_exists(session, "inspiration_sources", "last_status"),
        "inspiration_sources.consecutive_failures": await _column_exists(session, "inspiration_sources", "consecutive_failures"),
        "inspiration_runs.outcome": await _column_exists(session, "inspiration_runs", "outcome"),
        "inspiration_runs.metrics": await _column_exists(session, "inspiration_runs", "metrics"),
    }
    return {
        "report_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "alembic_version": await _alembic_version(session),
        "users": users,
        "user_ids_sha256": _sha256_lines([row["id"] for row in users]),
        "entities": entities,
        "identities": await _identity_snapshot(session),
        "guards": {
            "legacy_phone_users": legacy_phone_users,
            "casefold_email_duplicates": casefold_duplicates,
            "snapshot_duplicate_groups": snapshot_duplicates,
            "columns_029": columns_029,
        },
    }


def _compare_with_baseline(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    phase: str,
    expected_version: str,
) -> dict[str, Any]:
    errors: list[str] = []
    if current.get("alembic_version") != expected_version:
        errors.append(
            f"Alembic 版本为 {current.get('alembic_version') or 'unknown'}，预期 {expected_version}"
        )
    if current.get("user_ids_sha256") != baseline.get("user_ids_sha256"):
        errors.append("用户 ID 集合与迁移前基线不一致")
    for table_name, before_entity in baseline.get("entities", {}).items():
        after_entity = current.get("entities", {}).get(table_name)
        if after_entity != before_entity:
            errors.append(f"{table_name} 的数量、ID 或所有权摘要与基线不一致")
    guards = current.get("guards", {})
    if int(guards.get("legacy_phone_users", 0)) != 0:
        errors.append("存在手机号伪邮箱用户，禁止按简单绑定流程继续")
    if int(guards.get("casefold_email_duplicates", 0)) != 0:
        errors.append("存在大小写归一化后的重复邮箱")
    if int(guards.get("snapshot_duplicate_groups", 0)) != 0:
        errors.append("inspiration_source_snapshots 存在重复 (source_id, run_id)")

    user_count = len(current.get("users", []))
    identities = current.get("identities", {})
    provider_counts = identities.get("provider_counts", {})
    provider_user_counts = identities.get("provider_user_counts", {})
    if phase in {"after-migration", "after-binding"}:
        if not identities.get("exists"):
            errors.append("user_identities 表不存在")
        if int(provider_counts.get(EMAIL_PROVIDER, 0)) != user_count:
            errors.append("email identity 数量不等于用户数")
        if int(provider_user_counts.get(EMAIL_PROVIDER, 0)) != user_count:
            errors.append("并非每个用户都恰好拥有 email identity")
        if int(identities.get("email_mismatches", 0)) != 0:
            errors.append("email identity 与 users 邮箱或密码不一致")
        if int(identities.get("duplicate_provider_identifiers", 0)) != 0:
            errors.append("user_identities 存在重复 provider/identifier")
        columns_029 = guards.get("columns_029", {})
        missing_029 = sorted(name for name, exists in columns_029.items() if not exists)
        if missing_029:
            errors.append(f"029 目标列缺失：{missing_029}")
    if phase == "after-migration" and int(provider_counts.get(PHONE_PROVIDER, 0)) != 0:
        errors.append("人工绑定前不应存在 phone identity")
    if phase == "after-binding":
        if int(provider_counts.get(PHONE_PROVIDER, 0)) != user_count:
            errors.append("phone identity 数量不等于用户数")
        if int(provider_user_counts.get(PHONE_PROVIDER, 0)) != user_count:
            errors.append("并非每个用户都恰好拥有 phone identity")
        if int(identities.get("count", 0)) != user_count * 2:
            errors.append("绑定后 identity 总数不等于用户数的两倍")
    return {"ok": not errors, "errors": errors}


def _load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseIdentityError(f"无法读取基线报告：{path}") from error
    if not isinstance(payload, dict):
        raise ReleaseIdentityError("基线报告不是 JSON 对象")
    return payload


async def audit(args: argparse.Namespace) -> int:
    async with async_session_factory() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        snapshot = await _snapshot(session)
        await session.rollback()

    report: dict[str, Any] = {"phase": args.phase, **snapshot}
    errors: list[str] = []
    if snapshot.get("alembic_version") != args.expected_version:
        errors.append(
            f"Alembic 版本为 {snapshot.get('alembic_version') or 'unknown'}，预期 {args.expected_version}"
        )
    if args.phase == "before":
        if snapshot.get("identities", {}).get("exists"):
            errors.append("迁移前不应存在 user_identities 表")
        guards = snapshot.get("guards", {})
        if int(guards.get("legacy_phone_users", 0)) != 0:
            errors.append("迁移前存在手机号伪邮箱用户")
        if int(guards.get("casefold_email_duplicates", 0)) != 0:
            errors.append("迁移前存在大小写归一化后的重复邮箱")
        if int(guards.get("snapshot_duplicate_groups", 0)) != 0:
            errors.append("迁移前存在重复 inspiration snapshot")
        report["comparison"] = {"ok": not errors, "errors": errors}
    else:
        if not args.baseline:
            raise ReleaseIdentityError("after 阶段必须提供 --baseline")
        baseline_report = _load_report(Path(args.baseline).expanduser().resolve())
        comparison = _compare_with_baseline(
            baseline_report,
            snapshot,
            phase=args.phase,
            expected_version=args.expected_version,
        )
        if errors:
            comparison["errors"] = errors + comparison["errors"]
            comparison["ok"] = False
        report["comparison"] = comparison

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"审计报告已保存：{output}")
    if not report["comparison"]["ok"]:
        for error in report["comparison"]["errors"]:
            print(f"错误：{error}", file=sys.stderr)
        return 2
    print(f"审计通过：{args.phase}，Alembic={snapshot.get('alembic_version')}")
    return 0


async def bind(args: argparse.Namespace) -> int:
    mapping_path = Path(args.mapping).expanduser().resolve()
    mapping = _load_mapping(mapping_path)
    if args.apply and args.confirm != APPLY_CONFIRMATION:
        raise ReleaseIdentityError(
            f"提交绑定必须设置 --confirm {APPLY_CONFIRMATION}"
        )
    settings = get_settings()
    if args.apply and settings.environment.lower() == "production" and os.geteuid() != 0:
        raise ReleaseIdentityError("生产手机号绑定必须由受控的 root 发布会话执行")

    async with async_session_factory() as session:
        await session.begin()
        try:
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            await session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
            await session.execute(text("LOCK TABLE user_identities IN SHARE ROW EXCLUSIVE MODE"))
            version = await _alembic_version(session)
            if version != args.expected_version:
                raise ReleaseIdentityError(
                    f"数据库 Alembic 为 {version or 'unknown'}，预期 {args.expected_version}"
                )
            users = (await session.execute(select(User).order_by(User.id))).scalars().all()
            user_ids = {user.id for user in users}
            if set(mapping) != user_ids:
                missing = sorted(user_ids - set(mapping))
                unexpected = sorted(set(mapping) - user_ids)
                raise ReleaseIdentityError(
                    f"映射必须覆盖全部生产用户；缺少={missing}，非预期={unexpected}"
                )
            legacy_phone_users = int(
                await session.scalar(
                    text("SELECT count(*) FROM users WHERE email ~ :phone_placeholder_pattern"),
                    {"phone_placeholder_pattern": PHONE_PLACEHOLDER_EMAIL_PATTERN},
                )
                or 0
            )
            if legacy_phone_users:
                raise ReleaseIdentityError("发现手机号伪邮箱用户，禁止执行简单绑定")

            identities = (
                await session.execute(select(UserIdentity).with_for_update())
            ).scalars().all()
            phone_owner = {
                identity.identifier: identity.user_id
                for identity in identities
                if identity.provider == PHONE_PROVIDER
            }
            for user_id, phone in mapping.items():
                owner = phone_owner.get(phone)
                if owner and owner != user_id:
                    raise ReleaseIdentityError("目标手机号已绑定其他业务用户")
                if owner == user_id:
                    continue
                identity_id = "identity-" + hashlib.sha256(
                    f"{user_id}:phone:{phone}".encode("utf-8")
                ).hexdigest()[:24]
                session.add(
                    UserIdentity(
                        id=identity_id,
                        user_id=user_id,
                        provider=PHONE_PROVIDER,
                        identifier=phone,
                        verified_at=datetime.now(timezone.utc),
                    )
                )
            await session.flush()

            snapshot = await _snapshot(session)
            baseline = _load_report(Path(args.baseline).expanduser().resolve())
            comparison = _compare_with_baseline(
                baseline,
                snapshot,
                phase="after-binding",
                expected_version=args.expected_version,
            )
            if not comparison["ok"]:
                raise ReleaseIdentityError("；".join(comparison["errors"]))

            summary = [
                f"{user_id} -> {_mask_identifier(PHONE_PROVIDER, phone)}"
                for user_id, phone in sorted(mapping.items())
            ]
            if args.apply:
                await session.commit()
                action = "手机号身份绑定已提交"
            else:
                await session.rollback()
                action = "手机号身份绑定演练通过，事务已回滚"
            print(action)
            for line in summary:
                print(f"  {line}")
            return 0
        except Exception:
            await session.rollback()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="VideoX 发布用户身份审计与手机号绑定")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="生成只读迁移审计报告")
    audit_parser.add_argument(
        "--phase", choices=("before", "after-migration", "after-binding"), required=True
    )
    audit_parser.add_argument("--expected-version", required=True)
    audit_parser.add_argument("--baseline")
    audit_parser.add_argument("--output", required=True)

    bind_parser = subparsers.add_parser("bind", help="事务性绑定手机号身份")
    bind_parser.add_argument("--mapping", required=True)
    bind_parser.add_argument("--baseline", required=True)
    bind_parser.add_argument("--expected-version", required=True)
    bind_parser.add_argument("--apply", action="store_true")
    bind_parser.add_argument("--confirm", default="")

    args = parser.parse_args()
    try:
        if args.command == "audit":
            raise SystemExit(asyncio.run(audit(args)))
        raise SystemExit(asyncio.run(bind(args)))
    except (OSError, ReleaseIdentityError, ValueError) as error:
        parser.exit(1, f"发布身份迁移失败：{error}\n")


if __name__ == "__main__":
    main()
