import unittest
import io
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import ValidationError
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.api.assets import (
    _decode_cursor,
    _encode_cursor,
    _probe_image,
    _validate_upload_size,
    asset_out,
)
from app.api.billing import InvoiceCreateRequest, UpgradeRequest
from app.api.generate import _generation_prompt, _resolve_shot_ids, router as generate_router
from app.api.inspiration import router as inspiration_router
from app.api.notifications import _job_feed_link, _job_feed_type, router as notifications_router
from app.api.projects import _idempotent_project_id, router as projects_router
from app.main import app
from app.models.asset import Asset, ProjectAssetLink
from app.models.job import Job
from app.models.project import Project, ProjectComposition, ProjectRevision
from app.models.script import Script, ScriptUnit, Shot, ShotMediaVersion
from app.schemas.project import (
    ProjectDocument,
    ProjectDocumentSettings,
    ScopeSelection,
    SceneDocument,
    ShotDocument,
    StoryboardDocument,
    WorkspaceSave,
)
from app.services.workspace import _apply_shot, save_workspace
from app.services.subscriptions import (
    add_billing_period,
    initial_subscription_values,
    purchased_period,
    renewed_period,
)
from app.services.quotas import (
    QuotaSnapshot,
    expected_usage_period,
    monthly_usage_period,
    reset_periodic_usage,
)
from app.services.task_dispatch import task_priority_for_rank
from app.models.user import Usage
from scripts.manage_test_account import (
    AccountCommandError,
    ensure_not_production,
    normalize_email,
    reset_ai_counters,
    validate_name,
    validate_password,
)

class TaskPriorityTests(unittest.TestCase):
    def test_team_precedes_pro_and_free(self):
        team = task_priority_for_rank(2)
        pro = task_priority_for_rank(1)
        free = task_priority_for_rank(0)
        self.assertLess(team, pro)
        self.assertLess(pro, free)
        self.assertEqual((team, pro, free), (0, 4, 9))


class GenerationPromptTests(unittest.TestCase):
    def test_bulk_generation_uses_each_shot_description(self):
        scene = ScriptUnit(intent="展示产品能力", narration_text="旁白内容")
        shot = Shot(description="机器人在未来实验室中启动", unit=scene)

        prompt = _generation_prompt(
            shot,
            {
                "use_shot_descriptions": True,
                "additional_instruction": "保持主角外观一致",
                "style": "电影质感",
            },
            "prompt",
        )

        self.assertEqual(
            prompt,
            "机器人在未来实验室中启动。全局补充要求：保持主角外观一致。视觉风格：电影质感。",
        )

    def test_bulk_generation_falls_back_to_scene_intent(self):
        scene = ScriptUnit(intent="展示产品能力", narration_text="旁白内容")
        shot = Shot(description="", unit=scene)

        prompt = _generation_prompt(
            shot,
            {"use_shot_descriptions": True, "style": "真实纪实"},
            "prompt",
        )

        self.assertEqual(prompt, "展示产品能力。视觉风格：真实纪实。")

    def test_single_shot_generation_keeps_explicit_description(self):
        scene = ScriptUnit(intent="不应覆盖显式描述")
        shot = Shot(description="数据库中的旧描述", unit=scene)

        prompt = _generation_prompt(
            shot,
            {"prompt": "用户为当前镜头修改的描述", "style": "科技未来"},
            "prompt",
        )

        self.assertEqual(prompt, "用户为当前镜头修改的描述。视觉风格：科技未来。")


class UploadSizeValidationTests(unittest.TestCase):
    def test_empty_file_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            _validate_upload_size(0, max_size_gb=1)
        self.assertEqual(context.exception.status_code, 400)

    def test_non_empty_file_is_accepted(self):
        _validate_upload_size(1, max_size_gb=1)

    def test_exactly_one_gib_is_accepted(self):
        _validate_upload_size(1024 * 1024 * 1024, max_size_gb=1)

    def test_one_byte_over_one_gib_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            _validate_upload_size(1024 * 1024 * 1024 + 1, max_size_gb=1)
        self.assertEqual(context.exception.status_code, 413)
        self.assertIn("1 GiB", context.exception.detail)


class MembershipSubscriptionTests(unittest.TestCase):
    def test_monthly_period_clamps_month_end(self):
        start = datetime(2026, 1, 31, 8, 30, tzinfo=timezone.utc)
        self.assertEqual(
            add_billing_period(start, "monthly"),
            datetime(2026, 2, 28, 8, 30, tzinfo=timezone.utc),
        )

    def test_yearly_period_handles_leap_day(self):
        start = datetime(2024, 2, 29, 8, 30, tzinfo=timezone.utc)
        self.assertEqual(
            add_billing_period(start, "yearly"),
            datetime(2025, 2, 28, 8, 30, tzinfo=timezone.utc),
        )

    def test_existing_free_user_gets_permanent_active_subscription(self):
        values = initial_subscription_values(0, datetime(2026, 8, 11, tzinfo=timezone.utc))
        self.assertEqual(values["status"], "active")
        self.assertEqual(values["billing_cycle"], "permanent")
        self.assertEqual(values["provider"], "system")
        self.assertIsNone(values["current_period_end"])

    def test_existing_paid_user_gets_internal_subscription_without_fake_expiry(self):
        values = initial_subscription_values(2, datetime(2026, 8, 11, tzinfo=timezone.utc))
        self.assertEqual(values["status"], "internal")
        self.assertEqual(values["billing_cycle"], "permanent")
        self.assertEqual(values["provider"], "internal")
        self.assertIsNone(values["current_period_end"])

    def test_early_renewal_extends_from_existing_expiry(self):
        start = datetime(2026, 8, 11, tzinfo=timezone.utc)
        current_end = datetime(2026, 9, 11, tzinfo=timezone.utc)
        period_start, period_end = renewed_period(
            current_start=start,
            current_end=current_end,
            current_status="active",
            billing_cycle="monthly",
            now=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(period_start, start)
        self.assertEqual(period_end, datetime(2026, 10, 11, tzinfo=timezone.utc))

    def test_expired_renewal_restarts_from_payment_time(self):
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        period_start, period_end = renewed_period(
            current_start=datetime(2026, 8, 11, tzinfo=timezone.utc),
            current_end=datetime(2026, 9, 11, tzinfo=timezone.utc),
            current_status="expired",
            billing_cycle="monthly",
            now=now,
        )
        self.assertEqual(period_start, now)
        self.assertEqual(period_end, datetime(2026, 11, 20, tzinfo=timezone.utc))

    def test_cross_tier_upgrade_starts_a_fresh_period(self):
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        period_start, period_end = purchased_period(
            current_membership_id="membership-pro",
            target_membership_id="membership-team",
            current_start=datetime(2026, 8, 11, tzinfo=timezone.utc),
            current_end=datetime(2026, 9, 11, tzinfo=timezone.utc),
            current_status="active",
            billing_cycle="monthly",
            now=now,
        )
        self.assertEqual(period_start, now)
        self.assertEqual(period_end, datetime(2026, 10, 1, tzinfo=timezone.utc))

    def test_same_tier_purchase_extends_the_existing_period(self):
        period_start, period_end = purchased_period(
            current_membership_id="membership-pro",
            target_membership_id="membership-pro",
            current_start=datetime(2026, 8, 11, tzinfo=timezone.utc),
            current_end=datetime(2026, 9, 11, tzinfo=timezone.utc),
            current_status="active",
            billing_cycle="monthly",
            now=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(period_start, datetime(2026, 8, 11, tzinfo=timezone.utc))
        self.assertEqual(period_end, datetime(2026, 10, 11, tzinfo=timezone.utc))

    def test_upgrade_request_rejects_unknown_billing_cycle(self):
        with self.assertRaises(ValidationError):
            UpgradeRequest(membership_id="membership-pro", billing_cycle="weekly")


class UsageQuotaTests(unittest.TestCase):
    def test_month_end_usage_anchor_does_not_drift(self):
        anchor = datetime(2026, 1, 31, 8, 30, tzinfo=timezone.utc)
        self.assertEqual(
            monthly_usage_period(anchor, datetime(2026, 3, 15, tzinfo=timezone.utc)),
            (
                datetime(2026, 2, 28, 8, 30, tzinfo=timezone.utc),
                datetime(2026, 3, 31, 8, 30, tzinfo=timezone.utc),
            ),
        )
        self.assertEqual(
            monthly_usage_period(anchor, datetime(2026, 3, 31, 8, 30, tzinfo=timezone.utc)),
            (
                datetime(2026, 3, 31, 8, 30, tzinfo=timezone.utc),
                datetime(2026, 4, 30, 8, 30, tzinfo=timezone.utc),
            ),
        )

    def test_expired_subscription_starts_free_cycle_from_paid_expiry(self):
        subscription = SimpleNamespace(
            status="expired",
            current_period_start=datetime(2026, 7, 11, tzinfo=timezone.utc),
            current_period_end=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(
            expected_usage_period(subscription, datetime(2026, 8, 20, tzinfo=timezone.utc)),
            (
                datetime(2026, 8, 11, tzinfo=timezone.utc),
                datetime(2026, 9, 11, tzinfo=timezone.utc),
            ),
        )

    def test_period_reset_preserves_storage_but_clears_periodic_usage(self):
        usage = SimpleNamespace(
            processing_seconds_used=601,
            ai_image_used=7,
            ai_video_used=3,
            storage_used_mb=512.5,
            export_used=4,
            billing_cycle_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            billing_cycle_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 9, 1, tzinfo=timezone.utc)
        reset_periodic_usage(usage, start, end)
        self.assertEqual(usage.processing_seconds_used, 0)
        self.assertEqual(usage.ai_image_used, 0)
        self.assertEqual(usage.ai_video_used, 0)
        self.assertEqual(usage.export_used, 0)
        self.assertEqual(usage.storage_used_mb, 512.5)
        self.assertEqual(usage.billing_cycle_start, start)
        self.assertEqual(usage.billing_cycle_end, end)

    def test_processing_minutes_api_rounds_partial_minute_up(self):
        usage = Usage(user_id="quota-user", processing_seconds_used=61)
        self.assertEqual(usage.processing_minutes_used, 2)

    def test_quota_snapshot_remaining_excludes_used_and_reserved(self):
        snapshot = QuotaSnapshot(
            quota_type="ai_image",
            limit=10,
            used=4,
            reserved=3,
            requested=1,
        )
        self.assertEqual(snapshot.remaining, 3)


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


class WorkspaceSchemaTests(unittest.TestCase):
    def test_shot_source_range_rejects_reverse_range(self):
        with self.assertRaises(ValidationError):
            ShotDocument(source_start_ms=2000, source_end_ms=1000)

    def test_script_and_composition_are_project_unique(self):
        script_constraints = {constraint.name for constraint in Script.__table__.constraints}
        self.assertIn("uq_scripts_project_id", script_constraints)
        self.assertTrue(ProjectComposition.__table__.c.project_id.primary_key)

    def test_revision_and_asset_link_have_scoped_unique_constraints(self):
        revision_constraints = {constraint.name for constraint in ProjectRevision.__table__.constraints}
        link_constraints = {constraint.name for constraint in ProjectAssetLink.__table__.constraints}
        self.assertIn("uq_project_revision_number", revision_constraints)
        self.assertIn("uq_project_asset_role", link_constraints)

    def test_global_asset_has_owner_and_no_project_column(self):
        self.assertFalse(Asset.__table__.c.owner_id.nullable)
        self.assertNotIn("project_id", Asset.__table__.c)

    def test_global_job_can_exist_without_project(self):
        self.assertFalse(Job.__table__.c.owner_id.nullable)
        self.assertTrue(Job.__table__.c.project_id.nullable)


class AssetCursorAndImageTests(unittest.TestCase):
    def test_cursor_round_trip_preserves_sort_key(self):
        created_at = datetime(2026, 8, 17, 10, 30, tzinfo=timezone.utc)
        asset = SimpleNamespace(id="asset-123", created_at=created_at)
        self.assertEqual(_decode_cursor(_encode_cursor(asset)), (created_at, "asset-123"))

    def test_invalid_cursor_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            _decode_cursor("not-a-valid-cursor")
        self.assertEqual(context.exception.status_code, 422)

    def test_real_png_is_detected_with_dimensions(self):
        stream = io.BytesIO()
        Image.new("RGB", (32, 18), color=(10, 20, 30)).save(stream, format="PNG")
        stream.seek(0)
        result = _probe_image(UploadFile(file=stream, filename="cover.png"))
        self.assertEqual(result["format"], "PNG")
        self.assertEqual((result["width"], result["height"]), (32, 18))
        self.assertEqual(result["mime_type"], "image/png")

    def test_asset_summary_does_not_touch_lazy_segments(self):
        now = datetime(2026, 8, 17, 10, 30, tzinfo=timezone.utc)

        class LazyAsset(SimpleNamespace):
            @property
            def segments(self):
                raise AssertionError("素材摘要不应访问 lazy segments")

        result = asset_out(
            LazyAsset(
                id="asset-123",
                owner_id="user-1",
                name="cover.png",
                media_type="image",
                source_type="upload",
                status="ready",
                processing_status="ready",
                mime_type="image/png",
                duration_ms=0,
                width=32,
                height=18,
                has_audio=False,
                file_size_mb=0.1,
                tags=[],
                recognition={},
                preview_path=None,
                file_path=None,
                thumbnail_path=None,
                created_at=now,
                updated_at=now,
            ),
            include_segments=False,
        )
        self.assertEqual(result.segments, [])


class WorkspaceSubtitleTests(unittest.TestCase):
    @staticmethod
    def _shot_and_scene(*, subtitle="旧旁白", overridden=False):
        scene = ScriptUnit(id="scene-1", narration_text="新旁白", revision=2)
        shot = Shot(
            id="shot-1",
            unit=scene,
            subtitle_text=subtitle,
            subtitle_overridden=overridden,
            subtitle_source_revision=1,
            duration_ms=4000,
            revision=0,
        )
        return shot, scene

    def test_narration_change_updates_derived_subtitle(self):
        shot, scene = self._shot_and_scene()
        incoming = ShotDocument(id=shot.id, subtitle_text="旧旁白", duration_ms=4000)
        _apply_shot(shot, incoming, scene, True, None)
        self.assertEqual(shot.subtitle_text, "新旁白")
        self.assertFalse(shot.subtitle_overridden)
        self.assertEqual(shot.subtitle_source_revision, 2)

    def test_narration_change_keeps_explicit_override(self):
        shot, scene = self._shot_and_scene(subtitle="自定义字幕", overridden=True)
        incoming = ShotDocument(
            id=shot.id,
            subtitle_text="自定义字幕",
            subtitle_overridden=True,
            duration_ms=4000,
        )
        _apply_shot(shot, incoming, scene, True, None)
        self.assertEqual(shot.subtitle_text, "自定义字幕")
        self.assertTrue(shot.subtitle_overridden)

    def test_override_can_be_reset_to_narration(self):
        shot, scene = self._shot_and_scene(subtitle="自定义字幕", overridden=True)
        incoming = ShotDocument(
            id=shot.id,
            subtitle_text="新旁白",
            subtitle_overridden=False,
            duration_ms=4000,
        )
        _apply_shot(shot, incoming, scene, True, None)
        self.assertEqual(shot.subtitle_text, "新旁白")
        self.assertFalse(shot.subtitle_overridden)

    def test_selected_media_version_must_belong_to_shot(self):
        shot, scene = self._shot_and_scene()
        incoming = ShotDocument(
            id=shot.id,
            subtitle_text="新旁白",
            selected_media_version_id="missing-version",
            duration_ms=4000,
        )
        with self.assertRaises(HTTPException) as context:
            _apply_shot(shot, incoming, scene, False, None)
        self.assertEqual(context.exception.status_code, 422)

    def test_selecting_media_version_updates_asset_and_mode(self):
        shot, scene = self._shot_and_scene()
        version = ShotMediaVersion(
            id="version-1",
            shot=shot,
            asset_id="asset-image",
            kind="generated_image",
            operation="image",
            status="ready",
            is_selected=False,
        )
        shot.media_versions.append(version)
        incoming = ShotDocument(
            id=shot.id,
            subtitle_text="新旁白",
            selected_media_version_id=version.id,
            duration_ms=4000,
        )
        _apply_shot(shot, incoming, scene, False, None)
        self.assertEqual(shot.selected_media_version_id, version.id)
        self.assertEqual(shot.asset_id, "asset-image")
        self.assertEqual(shot.visual_mode, "image")
        self.assertTrue(version.is_selected)


class WorkspaceSaveGuardTests(unittest.IsolatedAsyncioTestCase):
    class _Db:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            return None

    @staticmethod
    def _request(script_id: str, revision: int, scenes: list[SceneDocument]):
        return WorkspaceSave(
            expected_revision=revision,
            document=ProjectDocument(
                id=script_id,
                revision=revision,
                settings=ProjectDocumentSettings(
                    title="主脚本",
                    status="editing",
                    source_type="blank",
                ),
                storyboard=StoryboardDocument(scenes=scenes),
            ),
        )

    async def test_revision_conflict_is_409(self):
        project = SimpleNamespace(
            script=SimpleNamespace(id="script-1", revision=3),
            composition=SimpleNamespace(),
        )
        with self.assertRaises(HTTPException) as context:
            await save_workspace(
                SimpleNamespace(),
                project,
                SimpleNamespace(id="user-1"),
                self._request("script-1", 2, []),
            )
        self.assertEqual(context.exception.status_code, 409)

    async def test_autosave_cannot_implicitly_delete_scene(self):
        scene = ScriptUnit(id="scene-1", index=0, narration_text="旁白", revision=0)
        script = Script(
            id="script-1",
            title="主脚本",
            status="editing",
            revision=0,
            source_type="blank",
        )
        script.units.append(scene)
        project = SimpleNamespace(
            id="project-1",
            script=script,
            composition=ProjectComposition(project_id="project-1", revision=0),
        )
        with self.assertRaises(HTTPException) as context:
            await save_workspace(
                SimpleNamespace(),
                project,
                SimpleNamespace(id="user-1"),
                self._request("script-1", 0, []),
            )
        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("删除场景", context.exception.detail)

    async def test_new_scene_and_shot_can_be_saved_before_database_defaults_apply(self):
        project = Project(
            id="project-1",
            owner_id="user-1",
            name="新项目",
            initial="新",
            type="AI 科技 / 产品讲解",
            description="",
            status="draft",
            variant="stage",
        )
        script = Script(
            id="script-1",
            project=project,
            title="主脚本",
            status="editing",
            revision=0,
            source_type="blank",
            visual_config={},
            units=[],
        )
        composition = ProjectComposition(project=project, project_id=project.id, revision=0)
        request = self._request(
            script.id,
            0,
            [
                SceneDocument(
                    outline="开场",
                    narration_text="第一句旁白",
                    shots=[ShotDocument(description="建立镜头", duration_ms=3000)],
                )
            ],
        )

        await save_workspace(self._Db(), project, SimpleNamespace(id="user-1"), request)

        self.assertEqual(script.revision, 1)
        self.assertEqual(len(script.units), 1)
        self.assertEqual(script.units[0].revision, 1)
        self.assertEqual(len(script.units[0].shots), 1)
        self.assertEqual(script.units[0].shots[0].revision, 1)


class ScopeAndRouteTests(unittest.TestCase):
    @staticmethod
    def _project_graph():
        return SimpleNamespace(
            script=SimpleNamespace(
                units=[
                    SimpleNamespace(
                        id="scene-1",
                        shots=[SimpleNamespace(id="shot-1"), SimpleNamespace(id="shot-2")],
                    ),
                    SimpleNamespace(id="scene-2", shots=[SimpleNamespace(id="shot-3")]),
                ]
            )
        )

    def test_scene_scope_resolves_only_owned_shots(self):
        result = _resolve_shot_ids(
            self._project_graph(), ScopeSelection(type="scene", scene_ids=["scene-2"])
        )
        self.assertEqual(result, ["shot-3"])

    def test_foreign_shot_scope_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            _resolve_shot_ids(
                self._project_graph(), ScopeSelection(type="shot", shot_ids=["foreign-shot"])
            )
        self.assertEqual(context.exception.status_code, 422)

    def test_project_idempotency_is_deterministic_and_user_scoped(self):
        first = _idempotent_project_id("user-a", "create-project-123")
        self.assertEqual(first, _idempotent_project_id("user-a", "create-project-123"))
        self.assertNotEqual(first, _idempotent_project_id("user-b", "create-project-123"))

    def test_new_workspace_and_operation_routes_are_registered(self):
        project_paths = {route.path for route in projects_router.routes}
        generate_paths = {route.path for route in generate_router.routes}
        inspiration_paths = {route.path for route in inspiration_router.routes}
        notification_paths = {route.path for route in notifications_router.routes}
        self.assertIn("/{project_id}/workspace", project_paths)
        self.assertIn("/{project_id}/scenes/{scene_id}", project_paths)
        self.assertIn("/{project_id}/undo", project_paths)
        self.assertIn("/projects/{project_id}/operations", generate_paths)
        self.assertIn("/creation-previews/script", generate_paths)
        self.assertIn("/creation-previews/assets", generate_paths)
        self.assertIn("/tasks/{task_id}/run", inspiration_paths)
        self.assertIn("/feed", notification_paths)

    def test_notification_feed_projects_jobs_back_to_business_pages(self):
        project_link = _job_feed_link(SimpleNamespace(
            id="job-1", project_id="project-1", type="导出", subject_type="project"
        ))
        inspiration_link = _job_feed_link(SimpleNamespace(
            id="job-2", project_id=None, type="灵感采集", subject_type="inspiration_task"
        ))
        self.assertEqual(project_link, ("/workspace/projects/project-1?job=job-1", "打开项目"))
        self.assertEqual(inspiration_link, ("/workspace/inspiration?job=job-2", "查看灵感岛"))
        self.assertEqual(_job_feed_type("FAILED"), "error")
        self.assertEqual(_job_feed_type("SUCCEEDED"), "success")
        self.assertEqual(_job_feed_type("RUNNING"), "info")

    def test_removed_script_center_and_collaboration_routes_are_absent(self):
        paths = {route.path for route in app.routes}
        self.assertFalse(any(path.startswith("/api/scripts") for path in paths))
        self.assertFalse(any(path.startswith("/api/collaboration") for path in paths))
        self.assertTrue(any(path.startswith("/api/inspiration") for path in paths))


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
