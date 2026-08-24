"""只读清点并核对 020 -> 当前 head 工作区迁移。

在数据库副本上执行，不会运行 Alembic，也不会修改业务表：

    python scripts/workspace_migration_audit.py before --output /tmp/openvma-before.json
    # 单独执行 alembic upgrade head
    python scripts/workspace_migration_audit.py after \
        --before /tmp/openvma-before.json --output /tmp/openvma-after.json

脚本使用应用的 DATABASE_URL，在 REPEATABLE READ、READ ONLY 事务中查询。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.workspace_migration_audit import compare_workspace_migration  # noqa: E402


async def _scalar(connection, statement: str) -> Any:
    return (await connection.execute(text(statement))).scalar()


async def _count(connection, statement: str) -> int:
    return int(await _scalar(connection, statement) or 0)


async def _ids(connection, statement: str) -> list[str]:
    return sorted(str(value) for value in (await connection.execute(text(statement))).scalars().all() if value is not None)


async def _version(connection) -> str | None:
    exists = await _scalar(connection, "SELECT to_regclass('public.alembic_version') IS NOT NULL")
    if not exists:
        return None
    value = await _scalar(connection, "SELECT version_num FROM alembic_version LIMIT 1")
    return str(value) if value else None


async def snapshot_before(connection) -> dict[str, Any]:
    split_script_sql = """
        SELECT script_id FROM (
            SELECT p.id AS old_project_id, s.id AS script_id,
                   row_number() OVER (
                       PARTITION BY p.id
                       ORDER BY CASE WHEN s.id = p.source_script_id THEN 0
                                     WHEN NOT s.is_snapshot THEN 1 ELSE 2 END,
                                s.updated_at DESC, s.created_at DESC, s.id
                   ) AS rn
            FROM projects p JOIN scripts s ON s.project_id = p.id
        ) ranked WHERE rn > 1
    """
    orphan_candidate_predicate = """
        c.shot_id IS NULL AND (
            c.unit_id IS NULL OR NOT EXISTS (SELECT 1 FROM script_units su WHERE su.id = c.unit_id)
        )
    """
    counts = {
        "projects": await _count(connection, "SELECT count(*) FROM projects"),
        "projects_with_scripts": await _count(connection, "SELECT count(DISTINCT project_id) FROM scripts"),
        "projects_without_scripts": await _count(connection, "SELECT count(*) FROM projects p WHERE NOT EXISTS (SELECT 1 FROM scripts s WHERE s.project_id = p.id)"),
        "scripts": await _count(connection, "SELECT count(*) FROM scripts"),
        "extra_scripts": await _count(connection, f"SELECT count(*) FROM ({split_script_sql}) split"),
        "snapshot_scripts": await _count(connection, "SELECT count(*) FROM scripts WHERE is_snapshot = true"),
        "scenes": await _count(connection, "SELECT count(*) FROM script_units"),
        "shots": await _count(connection, "SELECT count(*) FROM shots"),
        "recovery_shots": await _count(connection, """
            SELECT count(DISTINCT c.unit_id)
            FROM candidates c
            WHERE c.shot_id IS NULL AND c.unit_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM script_units su WHERE su.id = c.unit_id)
              AND NOT EXISTS (SELECT 1 FROM shots s WHERE s.unit_id = c.unit_id)
        """),
        "candidates": await _count(connection, "SELECT count(*) FROM candidates"),
        "orphan_candidates": await _count(connection, f"SELECT count(*) FROM candidates c WHERE {orphan_candidate_predicate}"),
        "assets": await _count(connection, "SELECT count(*) FROM assets"),
        "segments": await _count(connection, "SELECT count(*) FROM clips"),
        "project_media": await _count(connection, "SELECT count(*) FROM project_media_items"),
        "convertible_project_media": await _count(connection, "SELECT count(*) FROM project_media_items WHERE asset_id IS NULL AND storage_path IS NOT NULL"),
        "cut_versions": await _count(connection, "SELECT count(*) FROM cut_versions"),
        "shot_generations": await _count(connection, "SELECT count(*) FROM shot_generations"),
        "successful_exports": await _count(connection, "SELECT count(*) FROM jobs WHERE type = '导出' AND status = 'SUCCEEDED' AND result_path IS NOT NULL"),
        "collaboration_members": await _count(connection, "SELECT count(*) FROM project_members"),
        "project_invitations": await _count(connection, "SELECT count(*) FROM project_invitations"),
        "jobs": await _count(connection, "SELECT count(*) FROM jobs"),
    }
    ids = {
        "projects": await _ids(connection, "SELECT id FROM projects"),
        "scripts": await _ids(connection, "SELECT id FROM scripts"),
        "split_scripts": await _ids(connection, split_script_sql),
        "scenes": await _ids(connection, "SELECT id FROM script_units"),
        "shots": await _ids(connection, "SELECT id FROM shots"),
        "assets": await _ids(connection, "SELECT id FROM assets"),
        "segments": await _ids(connection, "SELECT id FROM clips"),
        "candidates_retained": await _ids(connection, f"SELECT id FROM candidates c WHERE NOT ({orphan_candidate_predicate})"),
        "orphan_candidates": await _ids(connection, f"SELECT id FROM candidates c WHERE {orphan_candidate_predicate}"),
        "project_media": await _ids(connection, "SELECT id FROM project_media_items"),
        "convertible_project_media": await _ids(connection, "SELECT id FROM project_media_items WHERE asset_id IS NULL AND storage_path IS NOT NULL"),
        "cut_versions": await _ids(connection, "SELECT id FROM cut_versions"),
        "shot_generations": await _ids(connection, "SELECT id FROM shot_generations"),
        "successful_exports": await _ids(connection, "SELECT id FROM jobs WHERE type = '导出' AND status = 'SUCCEEDED' AND result_path IS NOT NULL"),
        "collaboration_members": await _ids(connection, "SELECT id FROM project_members"),
        "project_invitations": await _ids(connection, "SELECT id FROM project_invitations"),
        "jobs": await _ids(connection, "SELECT id FROM jobs"),
    }
    return {
        "report_version": 1,
        "phase": "before",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "alembic_version": await _version(connection),
        "counts": counts,
        "ids": ids,
    }


async def snapshot_after(connection) -> dict[str, Any]:
    counts = {
        "projects": await _count(connection, "SELECT count(*) FROM projects"),
        "scripts": await _count(connection, "SELECT count(*) FROM scripts"),
        "scenes": await _count(connection, "SELECT count(*) FROM script_units"),
        "shots": await _count(connection, "SELECT count(*) FROM shots"),
        "candidates": await _count(connection, "SELECT count(*) FROM candidates"),
        "assets": await _count(connection, "SELECT count(*) FROM assets"),
        "segments": await _count(connection, "SELECT count(*) FROM asset_segments"),
        "project_asset_links": await _count(connection, "SELECT count(*) FROM project_asset_links"),
        "shot_media_versions": await _count(connection, "SELECT count(*) FROM shot_media_versions"),
        "project_revisions": await _count(connection, "SELECT count(*) FROM project_revisions"),
        "project_compositions": await _count(connection, "SELECT count(*) FROM project_compositions"),
        "migration_audits": await _count(connection, "SELECT count(*) FROM migration_audits WHERE migration_name = '021_project_workspace'"),
        "jobs": await _count(connection, "SELECT count(*) FROM jobs"),
    }
    ids = {
        "projects": await _ids(connection, "SELECT id FROM projects"),
        "scripts": await _ids(connection, "SELECT id FROM scripts"),
        "scenes": await _ids(connection, "SELECT id FROM script_units"),
        "shots": await _ids(connection, "SELECT id FROM shots"),
        "assets": await _ids(connection, "SELECT id FROM assets"),
        "segments": await _ids(connection, "SELECT id FROM asset_segments"),
        "candidates_retained": await _ids(connection, "SELECT id FROM candidates"),
        "jobs": await _ids(connection, "SELECT id FROM jobs"),
    }
    archived_ids = {
        "projects": await _ids(connection, "SELECT project_id FROM project_revisions WHERE reason = 'migration_archive'"),
        "project_media": await _ids(connection, """
            SELECT item->>'id'
            FROM project_revisions revision
            CROSS JOIN LATERAL json_array_elements(COALESCE(revision.document_snapshot->'project_media', '[]'::json)) item
            WHERE revision.reason = 'migration_archive'
        """),
        "cut_versions": await _ids(connection, """
            SELECT item->>'id'
            FROM project_revisions revision
            CROSS JOIN LATERAL json_array_elements(COALESCE(revision.document_snapshot->'cut_versions', '[]'::json)) item
            WHERE revision.reason = 'migration_archive'
        """),
        "collaboration_members": await _ids(connection, """
            SELECT item->>'id'
            FROM project_revisions revision
            CROSS JOIN LATERAL json_array_elements(COALESCE(revision.document_snapshot->'collaboration'->'members', '[]'::json)) item
            WHERE revision.reason = 'migration_archive'
        """),
        "project_invitations": await _ids(connection, """
            SELECT item->>'id'
            FROM project_revisions revision
            CROSS JOIN LATERAL json_array_elements(COALESCE(revision.document_snapshot->'collaboration'->'invitations', '[]'::json)) item
            WHERE revision.reason = 'migration_archive'
        """),
    }
    converted_ids = {
        "project_media": await _ids(connection, "SELECT metadata->>'legacy_project_media_id' FROM assets WHERE metadata->>'legacy_project_media_id' IS NOT NULL"),
        "shot_generations": await _ids(connection, "SELECT metadata->>'legacy_generation_id' FROM assets WHERE metadata->>'legacy_generation_id' IS NOT NULL"),
        "successful_exports": await _ids(connection, "SELECT metadata->>'export_job_id' FROM assets WHERE metadata->>'export_job_id' IS NOT NULL"),
        "cut_versions": await _ids(connection, "SELECT metadata->>'legacy_cut_version_id' FROM project_revisions WHERE reason = 'migration_cut_recovery'"),
    }
    audit_ids = {
        "orphan_candidates": await _ids(connection, "SELECT source_id FROM migration_audits WHERE migration_name = '021_project_workspace' AND action = 'archived_orphan'"),
        "split_scripts": await _ids(connection, "SELECT source_id FROM migration_audits WHERE migration_name = '021_project_workspace' AND action IN ('split_project', 'snapshot_recovery_project')"),
    }
    violations = {
        "projects_without_exactly_one_script": await _count(connection, """
            SELECT count(*) FROM (
                SELECT p.id FROM projects p LEFT JOIN scripts s ON s.project_id = p.id
                GROUP BY p.id HAVING count(s.id) <> 1
            ) invalid
        """),
        "projects_without_composition": await _count(connection, "SELECT count(*) FROM projects p WHERE NOT EXISTS (SELECT 1 FROM project_compositions pc WHERE pc.project_id = p.id)"),
        "unlinked_assets": await _count(connection, "SELECT count(*) FROM assets a WHERE NOT EXISTS (SELECT 1 FROM project_asset_links link WHERE link.asset_id = a.id)"),
        "candidates_without_shot": await _count(connection, "SELECT count(*) FROM candidates c WHERE NOT EXISTS (SELECT 1 FROM shots s WHERE s.id = c.shot_id)"),
        "shot_versions_without_asset": await _count(connection, "SELECT count(*) FROM shot_media_versions version WHERE NOT EXISTS (SELECT 1 FROM assets a WHERE a.id = version.asset_id)"),
        "shot_versions_without_project_link": await _count(connection, """
            SELECT count(*)
            FROM shot_media_versions version
            JOIN shots shot ON shot.id = version.shot_id
            JOIN script_units scene ON scene.id = shot.unit_id
            JOIN scripts script ON script.id = scene.script_id
            WHERE NOT EXISTS (
                SELECT 1 FROM project_asset_links link
                WHERE link.project_id = script.project_id
                  AND link.asset_id = version.asset_id
                  AND link.role = 'shot_media'
            )
        """),
        "revisions_without_project": await _count(connection, "SELECT count(*) FROM project_revisions revision WHERE NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = revision.project_id)"),
    }
    return {
        "report_version": 1,
        "phase": "after",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "alembic_version": await _version(connection),
        "counts": counts,
        "ids": ids,
        "archived_ids": archived_ids,
        "converted_ids": converted_ids,
        "audit_ids": audit_ids,
        "violations": violations,
    }


async def collect(phase: str) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                has_new_domain = bool(await _scalar(connection, "SELECT to_regclass('public.project_revisions') IS NOT NULL"))
                if phase == "before" and has_new_domain:
                    raise RuntimeError("数据库已经存在 project_revisions，不能生成迁移前报告")
                if phase == "after" and not has_new_domain:
                    raise RuntimeError("数据库尚未存在 project_revisions，不能生成迁移后报告")
                return await (snapshot_before(connection) if phase == "before" else snapshot_after(connection))
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


def _write_report(report: dict[str, Any], output: str | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not output:
        print(payload, end="")
        return
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(target)
    print(f"报告已写入：{target}")


async def run(args: argparse.Namespace) -> int:
    report = await collect(args.phase)
    if args.phase == "after":
        if not args.before:
            raise ValueError("after 阶段必须提供 --before 报告")
        before = json.loads(Path(args.before).expanduser().read_text(encoding="utf-8"))
        report["comparison"] = compare_workspace_migration(before, report)
    _write_report(report, args.output)
    return 0 if report.get("comparison", {}).get("ok", True) else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="只读清点并核对 OpenVMA 021 工作区迁移")
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--before", help="迁移前 JSON 报告；after 阶段必填")
    parser.add_argument("--output", help="输出 JSON 文件；省略时写到 stdout")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"迁移核对失败：{error}\n")


if __name__ == "__main__":
    main()
