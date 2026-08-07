import unittest
from types import SimpleNamespace

from app.api.projects import router as projects_router
from app.api.scripts import _compute_metrics, router as scripts_router
from app.models.cut_version import CutVersion
from app.models.script import ShotGeneration
from app.tasks.generate_tasks import _record_generation


class _ScalarResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return _ScalarResult()

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


class ScriptMetricsTests(unittest.TestCase):
    def test_metrics_count_shots_and_all_selected_visual_types(self):
        units = [
            SimpleNamespace(
                duration=8,
                selected_clip_id=None,
                shots=[
                    SimpleNamespace(duration=4, selected_clip_id="clip-1", generated_image_path=None, generated_video_path=None, generated_effect_video_path=None),
                    SimpleNamespace(duration=5, selected_clip_id=None, generated_image_path="image.png", generated_video_path=None, generated_effect_video_path=None),
                    SimpleNamespace(duration=6, selected_clip_id=None, generated_image_path=None, generated_video_path=None, generated_effect_video_path=None),
                ],
            )
        ]
        metrics = _compute_metrics(units)
        self.assertEqual(metrics["unit_count"], 3)
        self.assertEqual(metrics["matched_count"], 2)
        self.assertEqual(metrics["progress"], 67)
        self.assertEqual(metrics["duration"], "00:15")


class GenerationHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_generation_is_selected_when_shot_has_no_visual(self):
        session = _FakeSession()
        shot = SimpleNamespace(
            id="shot-1",
            selected_clip_id=None,
            generated_image_path=None,
            generated_video_path=None,
            generated_effect_video_path=None,
            visual_mode=None,
            status="待编辑",
        )
        generation = await _record_generation(
            session,
            shot,
            job_id="job-1",
            kind="image",
            storage_path="generated/image-1.png",
            prompt="第一版",
        )
        self.assertTrue(generation.is_selected)
        self.assertEqual(shot.generated_image_path, "generated/image-1.png")
        self.assertEqual(shot.status, "已选择")
        self.assertEqual(len(session.added), 1)

    async def test_later_generation_becomes_candidate_without_overwriting_selection(self):
        session = _FakeSession()
        shot = SimpleNamespace(
            id="shot-1",
            selected_clip_id=None,
            generated_image_path="generated/image-1.png",
            generated_video_path=None,
            generated_effect_video_path=None,
            visual_mode="image",
            status="已选择",
        )
        generation = await _record_generation(
            session,
            shot,
            job_id="job-2",
            kind="image",
            storage_path="generated/image-2.png",
            prompt="第二版",
        )
        self.assertFalse(generation.is_selected)
        self.assertEqual(shot.generated_image_path, "generated/image-1.png")
        self.assertEqual(shot.status, "待确认")


class VersionContractTests(unittest.TestCase):
    def test_cut_version_has_project_scoped_unique_name(self):
        constraints = {constraint.name for constraint in CutVersion.__table__.constraints}
        self.assertIn("uq_cut_version_project_name", constraints)

    def test_generation_job_kind_is_idempotent(self):
        constraints = {constraint.name for constraint in ShotGeneration.__table__.constraints}
        self.assertIn("uq_shot_generation_job_kind", constraints)

    def test_new_editor_and_version_routes_are_registered(self):
        script_paths = {route.path for route in scripts_router.routes}
        project_paths = {route.path for route in projects_router.routes}
        self.assertIn("/{script_id}/editor-state", script_paths)
        self.assertIn("/{script_id}/shots/{shot_id}/generations/{generation_id}/select", script_paths)
        self.assertIn("/{project_id}/versions", project_paths)
        self.assertIn("/{project_id}/assets/import", project_paths)
