"""021 工作区迁移的纯比较规则，不连接数据库也可单元测试。"""

from __future__ import annotations

from typing import Any


def expected_after_counts(before: dict[str, Any]) -> dict[str, int]:
    counts = before["counts"]
    return {
        "projects": counts["projects"] + counts["extra_scripts"],
        "scripts": counts["scripts"] + counts["projects_without_scripts"],
        "scenes": counts["scenes"],
        "shots": counts["shots"] + counts["recovery_shots"],
        "candidates": counts["candidates"] - counts["orphan_candidates"],
        "segments": counts["segments"],
        "assets": (
            counts["assets"]
            + counts["convertible_project_media"]
            + counts["successful_exports"]
            + counts["shot_generations"]
        ),
        "shot_media_versions": counts["shot_generations"],
        "project_revisions": counts["projects"] + counts["extra_scripts"] + counts["cut_versions"],
        "project_compositions": counts["projects"] + counts["extra_scripts"],
        "migration_audits": counts["extra_scripts"] + counts["orphan_candidates"],
        "jobs": counts["jobs"],
    }


def compare_workspace_migration(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("phase") != "before":
        raise ValueError("before 报告的 phase 必须是 before")
    if after.get("phase") != "after":
        raise ValueError("after 报告的 phase 必须是 after")

    errors: list[str] = []
    warnings: list[str] = []
    expected = expected_after_counts(before)
    after_counts = after.get("counts", {})

    for name, expected_value in expected.items():
        actual = int(after_counts.get(name, -1))
        if actual != expected_value:
            errors.append(f"{name}: 预期 {expected_value}，实际 {actual}")

    before_ids = before.get("ids", {})
    after_ids = after.get("ids", {})
    for name in (
        "projects",
        "scripts",
        "scenes",
        "shots",
        "assets",
        "segments",
        "candidates_retained",
        "jobs",
    ):
        missing = sorted(set(before_ids.get(name, [])) - set(after_ids.get(name, [])))
        if missing:
            errors.append(f"{name}: 缺少迁移前 ID {missing[:20]}" + (f" 等 {len(missing)} 项" if len(missing) > 20 else ""))

    exact_id_checks = (
        ("project_media", before_ids.get("project_media", []), after.get("archived_ids", {}).get("project_media", [])),
        ("cut_versions", before_ids.get("cut_versions", []), after.get("archived_ids", {}).get("cut_versions", [])),
        ("collaboration_members", before_ids.get("collaboration_members", []), after.get("archived_ids", {}).get("collaboration_members", [])),
        ("project_invitations", before_ids.get("project_invitations", []), after.get("archived_ids", {}).get("project_invitations", [])),
        ("archive_projects", before_ids.get("projects", []), after.get("archived_ids", {}).get("projects", [])),
        ("converted_project_media", before_ids.get("convertible_project_media", []), after.get("converted_ids", {}).get("project_media", [])),
        ("converted_shot_generations", before_ids.get("shot_generations", []), after.get("converted_ids", {}).get("shot_generations", [])),
        ("converted_exports", before_ids.get("successful_exports", []), after.get("converted_ids", {}).get("successful_exports", [])),
        ("cut_revision_ids", before_ids.get("cut_versions", []), after.get("converted_ids", {}).get("cut_versions", [])),
        ("orphan_candidate_audits", before_ids.get("orphan_candidates", []), after.get("audit_ids", {}).get("orphan_candidates", [])),
        ("split_script_audits", before_ids.get("split_scripts", []), after.get("audit_ids", {}).get("split_scripts", [])),
    )
    for label, expected_ids, actual_ids in exact_id_checks:
        expected_set = set(expected_ids)
        actual_set = set(actual_ids)
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set)
        if missing:
            errors.append(f"{label}: 缺少 {missing[:20]}" + (f" 等 {len(missing)} 项" if len(missing) > 20 else ""))
        if unexpected:
            errors.append(f"{label}: 出现非预期 ID {unexpected[:20]}" + (f" 等 {len(unexpected)} 项" if len(unexpected) > 20 else ""))

    for name, value in after.get("violations", {}).items():
        if int(value) != 0:
            errors.append(f"迁移后不变量 {name} 有 {value} 条违规记录")

    if int(after_counts.get("project_asset_links", 0)) < int(after_counts.get("assets", 0)):
        errors.append("project_asset_links 少于 assets，至少一个迁移素材没有项目关联")

    if before.get("alembic_version") != "020_team_seats":
        warnings.append(
            f"迁移前版本为 {before.get('alembic_version') or 'unknown'}，正式 021 演练应从 020_team_seats 开始"
        )
    if after.get("alembic_version") != "022_normalize_workspace":
        warnings.append(
            f"迁移后版本为 {after.get('alembic_version') or 'unknown'}，当前目标 head 是 022_normalize_workspace"
        )

    return {
        "ok": not errors,
        "expected_counts": expected,
        "actual_counts": after_counts,
        "errors": errors,
        "warnings": warnings,
    }
