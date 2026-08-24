"""在明确隔离的一次性 PostgreSQL 中演练 020 -> 当前 head 迁移。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.workspace_migration_rehearsal import (  # noqa: E402
    RehearsalTarget,
    validate_rehearsal_target,
)


async def _assert_empty_target(target: RehearsalTarget) -> None:
    engine = create_async_engine(target.async_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            database_name = await connection.scalar(text("SELECT current_database()"))
            if database_name != target.database_name:
                raise RuntimeError(
                    f"连接实际落在 {database_name!r}，而不是 {target.database_name!r}"
                )
            table_count = int(
                await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_tables
                        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                        """
                    )
                )
                or 0
            )
            if table_count:
                raise RuntimeError(
                    f"演练数据库不是空库（发现 {table_count} 张用户表）；请销毁并重建临时容器"
                )
    finally:
        await engine.dispose()


def _run(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    cwd: Path,
    stdin=None,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        stdin=stdin,
        check=False,
    )
    if completed.returncode not in allowed_returncodes:
        raise subprocess.CalledProcessError(completed.returncode, command)
    return completed


def _restore_dump(
    dump_path: Path,
    *,
    target: RehearsalTarget,
    environment: dict[str, str],
    backend_dir: Path,
    restore_mode: str,
) -> None:
    local_pg_restore = shutil.which("pg_restore")
    selected_mode = restore_mode
    if selected_mode == "auto":
        selected_mode = "local" if local_pg_restore else "compose"

    if selected_mode == "local":
        if not local_pg_restore:
            raise RuntimeError("未找到 pg_restore；可改用 --restore-mode compose")
        _run(
            (
                local_pg_restore,
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                target.database_name,
                str(dump_path),
            ),
            environment=environment,
            cwd=backend_dir,
        )
        return

    project_dir = backend_dir.parent
    compose_file = project_dir / "compose.migration-rehearsal.yml"
    if shutil.which("docker") is None:
        raise RuntimeError("未找到 docker，无法通过临时 Compose 数据库恢复备份")
    if not compose_file.is_file():
        raise RuntimeError(f"迁移演练 Compose 文件不存在：{compose_file}")
    with dump_path.open("rb") as dump_stream:
        _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "exec",
                "-T",
                "rehearsal-db",
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--username",
                "openvma_rehearsal",
                "--dbname",
                target.database_name,
            ),
            environment=environment,
            cwd=project_dir,
            stdin=dump_stream,
        )


def _load_report(path: Path) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"无法读取演练报告：{path}") from error
    if not isinstance(report, dict):
        raise RuntimeError(f"演练报告不是 JSON 对象：{path}")
    return report


async def rehearse(args: argparse.Namespace) -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    dump_path = Path(args.dump).expanduser().resolve()
    report_dir = Path(args.report_dir).expanduser().resolve()

    if not dump_path.is_file() or dump_path.stat().st_size == 0:
        raise ValueError("--dump 必须指向非空的 PostgreSQL custom-format dump")
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("生产环境禁止运行迁移演练脚本")

    settings = get_settings()
    if settings.environment.lower() == "production":
        raise RuntimeError("应用配置为生产环境，禁止运行迁移演练脚本")
    target = validate_rehearsal_target(
        args.database_url,
        confirmation=args.confirm_database,
        application_database_url=settings.database_url,
    )
    await _assert_empty_target(target)

    report_dir.mkdir(parents=True, exist_ok=True)
    before_report = report_dir / "workspace-migration-before.json"
    after_report = report_dir / "workspace-migration-after.json"

    child_environment = os.environ.copy()
    child_environment.update(target.pg_environment)
    child_environment["DATABASE_URL"] = target.async_url.render_as_string(
        hide_password=False
    )
    child_environment["ENVIRONMENT"] = "migration-rehearsal"

    print(f"演练目标：{target.display_name}")
    print(f"恢复备份：{dump_path}")
    _restore_dump(
        dump_path,
        target=target,
        environment=child_environment,
        backend_dir=backend_dir,
        restore_mode=args.restore_mode,
    )

    _run(
        (
            sys.executable,
            "scripts/workspace_migration_audit.py",
            "before",
            "--output",
            str(before_report),
        ),
        environment=child_environment,
        cwd=backend_dir,
    )
    before = _load_report(before_report)
    if before.get("alembic_version") != "020_team_seats":
        raise RuntimeError(
            "备份必须位于 020_team_seats；"
            f"实际为 {before.get('alembic_version') or 'unknown'}"
        )

    _run(
        (sys.executable, "-m", "alembic", "upgrade", "head"),
        environment=child_environment,
        cwd=backend_dir,
    )
    _run(
        (
            sys.executable,
            "scripts/workspace_migration_audit.py",
            "after",
            "--before",
            str(before_report),
            "--output",
            str(after_report),
        ),
        environment=child_environment,
        cwd=backend_dir,
        allowed_returncodes=frozenset({0, 2}),
    )

    after = _load_report(after_report)
    if after.get("alembic_version") != "026_unified_narration_cues":
        raise RuntimeError(
            "迁移必须到达 026_unified_narration_cues；"
            f"实际为 {after.get('alembic_version') or 'unknown'}"
        )
    comparison = after.get("comparison", {})
    if not comparison.get("ok"):
        print(f"演练失败，差异报告：{after_report}", file=sys.stderr)
        return 2

    print(f"演练通过，迁移前报告：{before_report}")
    print(f"演练通过，迁移后报告：{after_report}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="在本机一次性 PostgreSQL 空库中恢复备份并演练工作区迁移"
    )
    parser.add_argument("--dump", required=True, help="020 基线 PostgreSQL custom-format dump")
    parser.add_argument("--database-url", required=True, help="本机一次性演练数据库 URL")
    parser.add_argument(
        "--confirm-database",
        required=True,
        help="必须逐字填写目标数据库名，例如 openvma_rehearsal_021",
    )
    parser.add_argument(
        "--report-dir",
        default="/tmp/openvma-migration-rehearsal",
        help="迁移前后 JSON 报告目录",
    )
    parser.add_argument(
        "--restore-mode",
        choices=("auto", "local", "compose"),
        default="auto",
        help="恢复方式；auto 优先使用本机 pg_restore，否则使用临时 Compose 数据库",
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(rehearse(args)))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"迁移演练失败：{error}\n")


if __name__ == "__main__":
    main()
