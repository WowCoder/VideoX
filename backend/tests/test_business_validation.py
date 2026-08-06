import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.api.billing import InvoiceCreateRequest
from app.api.scripts import router as scripts_router
from app.api.projects import router as projects_router
from app.schemas.project import ProjectTimelineUpdate, TimelineAudio, TimelineClip, TimelineTransition
from app.services.project_access import ROLE_LEVEL
from app.services.timeline_validation import validate_timeline_layout
from app.tasks.roughcut_tasks import _assemble_script_timeline, _update_job_status
from scripts.manage_test_account import (
    AccountCommandError,
    ensure_not_production,
    normalize_email,
    reset_ai_counters,
    validate_name,
    validate_password,
)


class FakeAsset:
    def __init__(self, asset_id: str, duration: float):
        self.id = asset_id
        self.duration = duration


class CollaborationRoleTests(unittest.TestCase):
    def test_role_order_is_read_edit_manage(self):
        self.assertLess(ROLE_LEVEL["viewer"], ROLE_LEVEL["editor"])
        self.assertLess(ROLE_LEVEL["editor"], ROLE_LEVEL["owner"])


class TestAccountManagementTests(unittest.TestCase):
    def test_production_environment_is_rejected(self):
        with self.assertRaises(AccountCommandError):
            ensure_not_production("production")

    def test_missing_environment_is_rejected(self):
        with self.assertRaises(AccountCommandError):
            ensure_not_production("")

    def test_email_is_normalized(self):
        self.assertEqual(normalize_email("  TEST@Example.COM "), "test@example.com")

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(AccountCommandError):
            normalize_email("not-an-email")

    def test_password_and_name_follow_registration_limits(self):
        self.assertEqual(validate_password("123456"), "123456")
        self.assertEqual(validate_name(" 测试账号 "), "测试账号")
        with self.assertRaises(AccountCommandError):
            validate_password("12345")
        with self.assertRaises(AccountCommandError):
            validate_name("   ")

    def test_reset_only_changes_ai_usage_fields(self):
        usage = SimpleNamespace(
            ai_image_used=7,
            ai_video_used=3,
            processing_minutes_used=12,
            storage_used_mb=34.5,
            export_used=6,
            billing_cycle_start="start",
            billing_cycle_end="end",
        )

        previous = reset_ai_counters(usage)

        self.assertEqual(previous, (7, 3))
        self.assertEqual(usage.ai_image_used, 0)
        self.assertEqual(usage.ai_video_used, 0)
        self.assertEqual(usage.processing_minutes_used, 12)
        self.assertEqual(usage.storage_used_mb, 34.5)
        self.assertEqual(usage.export_used, 6)
        self.assertEqual(usage.billing_cycle_start, "start")
        self.assertEqual(usage.billing_cycle_end, "end")


class TimelineValidationTests(unittest.TestCase):
    def test_audio_editing_parameters_use_export_field_names(self):
        audio = TimelineAudio(
            volume=125,
            muted=True,
            denoise=True,
            fade_in=1.5,
            fade_out=2.5,
        )
        self.assertEqual(audio.model_dump(), {
            "volume": 125.0,
            "muted": True,
            "denoise": True,
            "fade_in": 1.5,
            "fade_out": 2.5,
        })

    def test_transition_duration_has_upper_bound(self):
        with self.assertRaises(ValidationError):
            TimelineTransition(type="fade_black", duration=3.1)

    def test_timeline_rejects_unknown_track(self):
        with self.assertRaises(ValidationError):
            ProjectTimelineUpdate(
                version=0,
                clips=[{
                    "id": "clip-1",
                    "track": "unknown",
                    "start": 0,
                    "duration": 1,
                    "name": "invalid",
                }],
            )

    def test_video_track_rejects_overlap(self):
        asset = FakeAsset("asset-1", 20)
        issues = validate_timeline_layout(
            [
                {"track": "video", "name": "A", "asset_id": "asset-1", "start": 0, "duration": 5, "source_start": 0},
                {"track": "video", "name": "B", "asset_id": "asset-1", "start": 4, "duration": 3, "source_start": 5},
            ],
            {"asset-1": asset},
        )
        self.assertTrue(any("重叠" in issue for issue in issues))

    def test_clip_rejects_source_overflow(self):
        asset = FakeAsset("asset-1", 10)
        issues = validate_timeline_layout(
            [{"track": "video", "name": "A", "asset_id": "asset-1", "start": 0, "duration": 3, "source_start": 8}],
            {"asset-1": asset},
        )
        self.assertTrue(any("超出源素材时长" in issue for issue in issues))

    def test_timeline_clip_preserves_script_lineage(self):
        clip = TimelineClip(
            id="timeline-1",
            track="video",
            start=0,
            duration=4,
            name="开场镜头",
            asset_id="asset-1",
            source_clip_id="clip-1",
            source_script_id="script-source",
            source_unit_id="unit-source",
            source_shot_id="shot-source",
            snapshot_script_id="script-snapshot",
            snapshot_unit_id="unit-snapshot",
            snapshot_shot_id="shot-snapshot",
            origin="script_match",
            sync_status="synced",
        )
        dumped = clip.model_dump()
        self.assertEqual(dumped["source_shot_id"], "shot-source")
        self.assertEqual(dumped["snapshot_shot_id"], "shot-snapshot")
        self.assertEqual(dumped["origin"], "script_match")
        self.assertEqual(dumped["sync_status"], "synced")

    def test_script_placeholder_can_be_saved_but_not_exported(self):
        placeholder = {
            "track": "video",
            "name": "待补产品特写",
            "start": 0,
            "duration": 4,
            "origin": "script_placeholder",
        }
        self.assertEqual(
            validate_timeline_layout([placeholder], {}, allow_placeholders=True),
            [],
        )
        issues = validate_timeline_layout([placeholder], {})
        self.assertTrue(any("待补素材" in issue for issue in issues))

    def test_generated_script_media_does_not_require_asset_id(self):
        issues = validate_timeline_layout(
            [{
                "track": "video",
                "name": "AI 产品镜头",
                "start": 0,
                "duration": 4,
                "origin": "script_generated",
                "generated_media_path": "generated/project/shot/video.mp4",
                "generated_media_type": "video",
            }],
            {},
        )
        self.assertEqual(issues, [])


class RoughCutAssemblyTests(unittest.TestCase):
    @staticmethod
    def _script(units):
        return SimpleNamespace(id="snapshot-1", parent_script_id="source-1", units=units)

    @staticmethod
    def _unit(shots, *, text="一段完整台词", duration=8):
        return SimpleNamespace(
            id="snapshot-unit-1",
            source_unit_id="source-unit-1",
            outline="产品介绍",
            text=text,
            duration=duration,
            shots=shots,
        )

    @staticmethod
    def _shot(shot_id, index, duration):
        return SimpleNamespace(
            id=shot_id,
            source_shot_id=f"source-{shot_id}",
            index=index,
            description=f"分镜 {index + 1}",
            duration=duration,
        )

    def test_every_shot_keeps_its_script_time_and_subtitle_span(self):
        shot_1 = self._shot("shot-1", 0, 5)
        shot_2 = self._shot("shot-2", 1, 4)
        script = self._script([self._unit([shot_1, shot_2])])

        timeline, stats = _assemble_script_timeline(script, {
            "shot-1": {
                "kind": "asset",
                "asset_id": "asset-1",
                "source_clip_id": "clip-1",
                "source_start": 2,
                "source_duration": 3,
                "name": "真实素材",
                "variant": "stage",
            },
        })

        videos = [clip for clip in timeline if clip["track"] == "video"]
        subtitle = next(clip for clip in timeline if clip["track"] == "subtitle")
        self.assertEqual([clip["start"] for clip in videos], [0.0, 3.0, 5.0])
        self.assertEqual([clip["duration"] for clip in videos], [3.0, 2.0, 4.0])
        self.assertEqual([clip["origin"] for clip in videos], [
            "script_match", "script_placeholder", "script_placeholder",
        ])
        self.assertEqual(subtitle["start"], 0.0)
        self.assertEqual(subtitle["duration"], 9.0)
        self.assertEqual(subtitle["text"], "一段完整台词")
        self.assertEqual(stats, {
            "matched": 1,
            "generated": 0,
            "placeholder": 2,
            "completed": 0,
        })

    def test_generated_media_is_materialized_on_timeline(self):
        shot = self._shot("shot-ai", 0, 6)
        script = self._script([self._unit([shot])])
        timeline, stats = _assemble_script_timeline(script, {
            "shot-ai": {
                "kind": "generated",
                "generated_media_path": "generated/project/shot-ai/image.png",
                "generated_media_type": "image",
                "name": "AI 关键帧",
            },
        })
        video = next(clip for clip in timeline if clip["track"] == "video")
        self.assertEqual(video["origin"], "script_generated")
        self.assertEqual(video["duration"], 6.0)
        self.assertEqual(video["generated_media_type"], "image")
        self.assertEqual(stats, {
            "matched": 0,
            "generated": 1,
            "placeholder": 0,
            "completed": 1,
        })

    def test_unit_without_shots_still_creates_timed_placeholder_and_subtitle(self):
        script = self._script([self._unit([], duration=7)])
        timeline, stats = _assemble_script_timeline(script, {})
        video = next(clip for clip in timeline if clip["track"] == "video")
        subtitle = next(clip for clip in timeline if clip["track"] == "subtitle")
        self.assertEqual(video["origin"], "script_placeholder")
        self.assertEqual(video["duration"], 7.0)
        self.assertEqual(subtitle["duration"], 7.0)
        self.assertEqual(stats["placeholder"], 1)


class RoughCutJobStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_status_update_builds_statement_in_worker_scope(self):
        class FakeSession:
            statement = None

            async def execute(self, statement):
                self.statement = statement

        session = FakeSession()
        await _update_job_status(session, "job-1", "RUNNING", detail="正在装配")
        self.assertIsNotNone(session.statement)
        self.assertIn("UPDATE jobs", str(session.statement))


class ScriptRouteTests(unittest.TestCase):
    def test_snapshot_route_is_registered_before_dynamic_script_route(self):
        paths = [route.path for route in scripts_router.routes]
        self.assertIn("/snapshot", paths)
        self.assertLess(paths.index("/snapshot"), paths.index("/{script_id}"))

    def test_empty_timeline_assembly_route_is_registered(self):
        paths = [route.path for route in projects_router.routes]
        self.assertIn("/{project_id}/timeline/assemble-from-script", paths)


class InvoiceValidationTests(unittest.TestCase):
    def test_tax_number_only_accepts_letters_and_digits(self):
        with self.assertRaises(ValidationError):
            InvoiceCreateRequest(
                order_id="order-1",
                company_name="测试企业",
                tax_number="9131-INVALID",
                email="finance@example.com",
            )

    def test_valid_invoice_application(self):
        request = InvoiceCreateRequest(
            order_id="order-1",
            company_name="测试企业有限公司",
            tax_number="91310000QA12345678",
            email="finance@example.com",
        )
        self.assertEqual(request.order_id, "order-1")


if __name__ == "__main__":
    unittest.main()
