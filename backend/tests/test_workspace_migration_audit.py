"""021 工作区迁移清点报告的纯比较测试。"""

from __future__ import annotations

from copy import deepcopy
import unittest

from app.services.workspace_migration_audit import (
    compare_workspace_migration,
    expected_after_counts,
)


def _before_report() -> dict:
    return {
        "report_version": 1,
        "phase": "before",
        "alembic_version": "020_team_seats",
        "counts": {
            "projects": 2,
            "projects_without_scripts": 1,
            "scripts": 3,
            "extra_scripts": 2,
            "scenes": 5,
            "shots": 7,
            "recovery_shots": 2,
            "candidates": 11,
            "orphan_candidates": 1,
            "segments": 6,
            "assets": 13,
            "convertible_project_media": 2,
            "successful_exports": 1,
            "shot_generations": 3,
            "cut_versions": 4,
            "jobs": 8,
        },
        "ids": {
            "projects": ["project-1", "project-2"],
            "scripts": ["script-1", "script-2", "script-3"],
            "split_scripts": ["script-2", "script-3"],
            "scenes": ["scene-1", "scene-2"],
            "shots": ["shot-1", "shot-2"],
            "assets": ["asset-1", "asset-2"],
            "segments": ["segment-1", "segment-2"],
            "candidates_retained": ["candidate-1", "candidate-2"],
            "orphan_candidates": ["candidate-orphan"],
            "project_media": ["media-1", "media-2", "media-archived-only"],
            "convertible_project_media": ["media-1", "media-2"],
            "cut_versions": ["cut-1", "cut-2", "cut-3", "cut-4"],
            "shot_generations": ["generation-1", "generation-2", "generation-3"],
            "successful_exports": ["job-export-1"],
            "collaboration_members": ["member-1"],
            "project_invitations": ["invitation-1"],
            "jobs": ["job-1", "job-export-1"],
        },
    }


def _after_report(before: dict | None = None) -> dict:
    source = before or _before_report()
    expected = expected_after_counts(source)
    return {
        "report_version": 1,
        "phase": "after",
        "alembic_version": "022_normalize_workspace",
        "counts": {
            **expected,
            "project_asset_links": expected["assets"] + 4,
        },
        "ids": {
            "projects": ["project-1", "project-2", "project-split-1", "project-split-2"],
            "scripts": ["script-1", "script-2", "script-3", "script-blank"],
            "scenes": ["scene-1", "scene-2"],
            "shots": ["shot-1", "shot-2", "shot-recovery-1", "shot-recovery-2"],
            "assets": ["asset-1", "asset-2", "asset-converted"],
            "segments": ["segment-1", "segment-2"],
            "candidates_retained": ["candidate-1", "candidate-2"],
            "jobs": ["job-1", "job-export-1"],
        },
        "archived_ids": {
            "projects": ["project-1", "project-2"],
            "project_media": ["media-1", "media-2", "media-archived-only"],
            "cut_versions": ["cut-1", "cut-2", "cut-3", "cut-4"],
            "collaboration_members": ["member-1"],
            "project_invitations": ["invitation-1"],
        },
        "converted_ids": {
            "project_media": ["media-1", "media-2"],
            "shot_generations": ["generation-1", "generation-2", "generation-3"],
            "successful_exports": ["job-export-1"],
            "cut_versions": ["cut-1", "cut-2", "cut-3", "cut-4"],
        },
        "audit_ids": {
            "orphan_candidates": ["candidate-orphan"],
            "split_scripts": ["script-2", "script-3"],
        },
        "violations": {
            "projects_without_exactly_one_script": 0,
            "projects_without_composition": 0,
            "unlinked_assets": 0,
            "candidates_without_shot": 0,
            "shot_versions_without_asset": 0,
            "shot_versions_without_project_link": 0,
            "revisions_without_project": 0,
        },
    }


class WorkspaceMigrationAuditTests(unittest.TestCase):
    def test_expected_counts_cover_splits_recovery_and_conversions(self):
        self.assertEqual(
            expected_after_counts(_before_report()),
            {
                "projects": 4,
                "scripts": 4,
                "scenes": 5,
                "shots": 9,
                "candidates": 10,
                "segments": 6,
                "assets": 19,
                "shot_media_versions": 3,
                "project_revisions": 8,
                "project_compositions": 4,
                "migration_audits": 3,
                "jobs": 8,
            },
        )

    def test_matching_reports_are_accepted(self):
        before = _before_report()
        comparison = compare_workspace_migration(before, _after_report(before))

        self.assertTrue(comparison["ok"])
        self.assertEqual(comparison["errors"], [])
        self.assertEqual(comparison["warnings"], [])

    def test_core_count_mismatches_are_reported(self):
        for name in ("projects", "scripts", "shots", "segments", "assets", "jobs"):
            with self.subTest(name=name):
                before = _before_report()
                after = _after_report(before)
                after["counts"][name] += 1

                comparison = compare_workspace_migration(before, after)

                self.assertFalse(comparison["ok"])
                self.assertTrue(
                    any(error.startswith(f"{name}:") for error in comparison["errors"]),
                    comparison["errors"],
                )

    def test_missing_original_entity_id_is_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["ids"]["shots"].remove("shot-1")

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn("shots: 缺少迁移前 ID ['shot-1']", comparison["errors"])

    def test_missing_segment_and_job_ids_are_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["ids"]["segments"].remove("segment-1")
        after["ids"]["jobs"].remove("job-1")

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn("segments: 缺少迁移前 ID ['segment-1']", comparison["errors"])
        self.assertIn("jobs: 缺少迁移前 ID ['job-1']", comparison["errors"])

    def test_missing_cut_archive_is_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["archived_ids"]["cut_versions"].remove("cut-2")

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn("cut_versions: 缺少 ['cut-2']", comparison["errors"])

    def test_missing_project_media_conversion_is_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["converted_ids"]["project_media"].remove("media-1")

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn("converted_project_media: 缺少 ['media-1']", comparison["errors"])

    def test_missing_orphan_candidate_audit_is_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["audit_ids"]["orphan_candidates"] = []

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn("orphan_candidate_audits: 缺少 ['candidate-orphan']", comparison["errors"])

    def test_post_migration_violation_is_reported(self):
        before = _before_report()
        after = _after_report(before)
        after["violations"]["projects_without_composition"] = 2

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn(
            "迁移后不变量 projects_without_composition 有 2 条违规记录",
            comparison["errors"],
        )

    def test_version_warnings_do_not_hide_real_errors(self):
        before = _before_report()
        after = _after_report(before)
        before["alembic_version"] = "019_usage_quota_accounting"
        after["alembic_version"] = "021_project_workspace"
        after["counts"]["assets"] += 1

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertTrue(any(error.startswith("assets:") for error in comparison["errors"]))
        self.assertEqual(len(comparison["warnings"]), 2)

    def test_rejects_reports_with_wrong_phase(self):
        before = _before_report()
        after = _after_report(before)

        before["phase"] = "after"
        with self.assertRaisesRegex(ValueError, "before 报告的 phase"):
            compare_workspace_migration(before, after)

        before["phase"] = "before"
        after["phase"] = "before"
        with self.assertRaisesRegex(ValueError, "after 报告的 phase"):
            compare_workspace_migration(before, after)

    def test_unexpected_reconciliation_id_is_reported(self):
        before = _before_report()
        after = deepcopy(_after_report(before))
        after["converted_ids"]["successful_exports"].append("job-unknown")

        comparison = compare_workspace_migration(before, after)

        self.assertFalse(comparison["ok"])
        self.assertIn(
            "converted_exports: 出现非预期 ID ['job-unknown']",
            comparison["errors"],
        )


if __name__ == "__main__":
    unittest.main()
