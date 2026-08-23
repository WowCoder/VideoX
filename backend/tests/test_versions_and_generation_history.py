"""唯一主脚本、主成片和镜头媒体版本契约测试。"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.orm import Session, object_session

from app.models.project import ProjectComposition, ProjectRevision, ProjectUndoToken
from app.models.script import Script, ScriptUnit, Shot, ShotMediaVersion
from app.schemas.project import ShotDocument
from app.services.workspace import _apply_shot, _restore_shot, ensure_shot_material_history, load_project_workspace
from app.tasks.generate_tasks import _can_auto_select_media_version


class VersionModelContractTests(unittest.TestCase):
    def test_ai_result_only_auto_selects_for_unchanged_shot(self):
        self.assertTrue(_can_auto_select_media_version(7, 7))
        self.assertFalse(_can_auto_select_media_version(8, 7))

    def test_script_is_unique_per_project(self):
        constraints = {constraint.name for constraint in Script.__table__.constraints}
        self.assertIn("uq_scripts_project_id", constraints)

    def test_composition_project_id_is_the_primary_key(self):
        self.assertTrue(ProjectComposition.__table__.c.project_id.primary_key)

    def test_project_revision_number_is_unique_inside_project(self):
        constraints = {constraint.name for constraint in ProjectRevision.__table__.constraints}
        self.assertIn("uq_project_revision_number", constraints)

    def test_generation_job_kind_is_idempotent(self):
        constraints = {constraint.name for constraint in ShotMediaVersion.__table__.constraints}
        self.assertIn("uq_shot_media_version_job_kind", constraints)

    def test_selected_media_version_is_a_real_foreign_key(self):
        foreign_keys = {
            foreign_key.target_fullname
            for foreign_key in Shot.__table__.c.selected_media_version_id.foreign_keys
        }
        self.assertEqual(foreign_keys, {"shot_media_versions.id"})

    def test_undo_token_is_project_scoped_and_expires(self):
        self.assertFalse(ProjectUndoToken.__table__.c.project_id.nullable)
        self.assertFalse(ProjectUndoToken.__table__.c.expires_at.nullable)


class WorkspaceLockingContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_for_update_refreshes_cached_project_aggregate(self):
        project = SimpleNamespace(script=object(), composition=object())
        result = SimpleNamespace(scalar_one_or_none=lambda: project)
        session = SimpleNamespace(execute=AsyncMock(return_value=result))

        loaded = await load_project_workspace(
            session,
            "project-concurrent",
            "user-concurrent",
            for_update=True,
        )

        self.assertIs(loaded, project)
        statement = session.execute.await_args.args[0]
        self.assertIsNotNone(statement._for_update_arg)
        self.assertTrue(statement.get_execution_options()["populate_existing"])


class RestoreVersionHistoryTests(unittest.TestCase):
    def test_pending_shot_cascades_version_without_eager_foreign_key(self):
        session = Session()
        scene = ScriptUnit(id="scene-pending", narration_text="旁白", revision=0, shots=[])
        shot = Shot(
            id="shot-pending",
            unit=scene,
            asset_id="asset-pending",
            candidates=[],
            media_versions=[],
        )
        session.add(shot)

        version = ensure_shot_material_history(
            shot,
            asset_id="asset-pending",
            segment_id=None,
            source_start_ms=0,
            source_end_ms=4_000,
            origin="library",
            operation="library_selection",
            selected=True,
        )

        self.assertIsNotNone(version)
        self.assertIs(object_session(version), session)
        self.assertIs(shot.selected_media_version, version)
        self.assertIsNone(shot.selected_media_version_id)
        session.close()

    def test_manual_material_changes_create_deduplicated_history(self):
        scene = ScriptUnit(id="scene-history", narration_text="旁白", revision=2)
        source = Shot(
            id="shot-history",
            unit=scene,
            asset_id="asset-old",
            segment_id=None,
            visual_mode="image",
            source_start_ms=0,
            source_end_ms=4000,
            duration_ms=4000,
            subtitle_text="旁白",
            subtitle_overridden=False,
            subtitle_source_revision=2,
            revision=2,
            candidates=[],
            media_versions=[],
        )
        incoming = ShotDocument.model_validate({
            "id": source.id,
            "index": 0,
            "description": "新画面",
            "asset_id": "asset-new",
            "segment_id": "segment-new",
            "visual_mode": "video",
            "source_start_ms": 1000,
            "source_end_ms": 5000,
            "duration_ms": 4000,
            "subtitle_text": "旁白",
            "revision": 2,
        })

        _apply_shot(source, incoming, scene, False, None)

        self.assertEqual({item.asset_id for item in source.media_versions}, {"asset-old", "asset-new"})
        selected = next(item for item in source.media_versions if item.is_selected)
        self.assertEqual(selected.asset_id, "asset-new")
        self.assertIs(selected.shot, source)
        self.assertIs(source.selected_media_version, selected)
        self.assertEqual(selected.parameters["material_history"]["segment_id"], "segment-new")
        ensure_shot_material_history(
            source,
            asset_id="asset-new",
            segment_id="segment-new",
            source_start_ms=1000,
            source_end_ms=5000,
            origin="match",
            operation="match",
            selected=True,
        )
        self.assertEqual(len(source.media_versions), 2)

    def test_restore_shot_rebuilds_candidates_and_media_versions(self):
        scene = ScriptUnit(id="scene-restore", narration_text="恢复字幕")
        created_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
        data = ShotDocument.model_validate(
            {
                "id": "shot-restore",
                "index": 0,
                "description": "恢复的镜头",
                "duration_ms": 5000,
                "subtitle_text": "恢复字幕",
                "selected_media_version_id": "version-1",
                "candidates": [
                    {
                        "id": "candidate-1",
                        "segment_id": "segment-1",
                        "title": "候选素材",
                        "score": 88,
                    }
                ],
                "media_versions": [
                    {
                        "id": "version-1",
                        "asset_id": "asset-1",
                        "job_id": "job-1",
                        "parent_version_id": "version-source",
                        "kind": "generated_image",
                        "operation": "image",
                        "parameters": {"prompt": "测试"},
                        "status": "ready",
                        "is_selected": True,
                        "created_at": created_at.isoformat(),
                    }
                ],
            }
        )

        restored = _restore_shot(scene, data)

        self.assertEqual(restored.id, "shot-restore")
        self.assertEqual(restored.candidates[0].segment_id, "segment-1")
        self.assertEqual(restored.media_versions[0].asset_id, "asset-1")
        self.assertEqual(restored.media_versions[0].parent_version_id, "version-source")
        self.assertTrue(restored.media_versions[0].is_selected)
        # 循环外键必须等媒体版本 flush 后再由 undo_mutation 恢复。
        self.assertIsNone(restored.selected_media_version_id)


if __name__ == "__main__":
    unittest.main()
