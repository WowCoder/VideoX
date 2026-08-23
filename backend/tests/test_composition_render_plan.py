import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import AsyncMock

from app.api import generate, jobs
from app.schemas.job import JobOut
from app.services.composition_render_plan import compile_composition_render_plan
from app.tasks import export_tasks
from app.tasks.export_tasks import _target_dimensions, _video_filter
from app.tasks.script_tasks import normalize_generated_script


def ns(**values):
    return SimpleNamespace(**values)


def shot(shot_id, index, asset_id, **overrides):
    values = {
        "id": shot_id,
        "index": index,
        "description": shot_id,
        "duration_ms": 2000,
        "asset_id": asset_id,
        "selected_media_version_id": None,
        "media_versions": [],
        "source_start_ms": 0,
        "source_end_ms": 2000,
        "transform": {},
        "adjust": {},
        "motion": {},
        "audio_settings": {},
        "transition": {},
        "subtitle_text": "",
        "subtitle_settings": {},
    }
    values.update(overrides)
    return ns(**values)


def project(shots, *, global_audio=None, global_scopes=None, visual_layers=None, visual_settings=None, aspect_ratio="16:9"):
    scene = ns(id="scene-1", index=0, outline="Scene", shots=shots)
    return ns(
        script=ns(units=[scene]),
        composition=ns(
            aspect_ratio=aspect_ratio,
            fps=30,
            global_audio=global_audio or {},
            global_scopes=global_scopes or {"film": {}, "scenes": {}},
            visual_layers=visual_layers or {"items": []},
            visual_settings=visual_settings or {},
        ),
    )


class CompositionRenderPlanTests(unittest.TestCase):
    def test_music_precedence_merging_ducking_and_voice(self):
        shots = [
            shot("shot-1", 0, "video-1"),
            shot("shot-2", 1, "video-2"),
            shot(
                "shot-3", 2, "video-3",
                audio_settings={"backgroundMusic": {"assetId": "shot-music", "volume": 50}},
            ),
        ]
        plan = compile_composition_render_plan(project(
            shots,
            global_audio={
                "voiceAssetId": "voice", "voiceVolume": 80,
                "musicAssetId": "project-music", "musicVolume": 20,
                "duckingEnabled": True,
            },
            global_scopes={
                "film": {"backgroundMusic": {"assetId": "film-music", "volume": 30}},
                "scenes": {},
            },
        ))
        voice = next(item for item in plan.audio_clips if item["role"] == "voice")
        music = [item for item in plan.audio_clips if item["role"] == "music"]
        self.assertEqual((voice["asset_id"], voice["duration"], voice["loop"]), ("voice", 6.0, False))
        self.assertEqual(len(music), 2)
        self.assertEqual((music[0]["asset_id"], music[0]["start"], music[0]["duration"]), ("film-music", 0.0, 4.0))
        self.assertAlmostEqual(music[0]["audio"]["volume"], 15.6)
        self.assertEqual((music[1]["asset_id"], music[1]["start"], music[1]["duration"]), ("shot-music", 4.0, 2.0))
        self.assertAlmostEqual(music[1]["audio"]["volume"], 26.0)

    def test_scope_effects_visual_ranges_subtitles_and_transition(self):
        source = shot(
            "shot-1", 0, "video-1",
            subtitle_text="字幕",
            subtitle_settings={"position": "top", "fontSize": 21, "color": "#ffcc00"},
            transition={"type": "slide-left", "durationMs": 750},
            audio_settings={"soundEffects": [{"assetId": "shot-sfx", "atMs": 250, "durationMs": 500}]},
        )
        plan = compile_composition_render_plan(project(
            [source],
            global_scopes={
                "film": {
                    "soundEffects": [{"assetId": "film-sfx", "durationMs": 1000}],
                    "visualAssets": [{"assetId": "film-overlay", "opacity": 25}],
                },
                "scenes": {
                    "scene-1": {
                        "soundEffects": [{"assetId": "scene-sfx", "atMs": 100}],
                        "visualAssets": [{"assetId": "scene-overlay"}],
                    }
                },
            },
            visual_layers={"items": [
                {"id": "layer", "assetId": "timeline-overlay", "startMs": 500, "durationMs": 1000},
                {"assetId": "outside", "startMs": 3000, "durationMs": 1000},
            ]},
        ))
        self.assertEqual(plan.video_clips[0]["transition"]["duration"], 0.75)
        self.assertEqual(plan.video_clips[0]["fps"], 30)
        self.assertEqual(plan.subtitle_entries[0]["settings"]["position"], "top")
        self.assertEqual(plan.subtitle_entries[0]["settings"]["font_size"], 21)
        self.assertEqual({item["role"] for item in plan.audio_clips}, {"shot_sfx", "scene_sfx", "film_sfx"})
        self.assertEqual(
            {(item["role"], item["asset_id"], item["start"], item["duration"]) for item in plan.visual_layers},
            {
                ("film_visual", "film-overlay", 0.0, 2.0),
                ("scene_visual", "scene-overlay", 0.0, 2.0),
                ("timeline_visual", "timeline-overlay", 0.5, 1.0),
            },
        )

    def test_selected_media_version_wins_and_missing_asset_fails(self):
        version = ns(id="version-1", asset_id="generated", is_selected=False)
        selected = shot(
            "shot-1", 0, "original",
            selected_media_version_id="version-1", media_versions=[version],
        )
        plan = compile_composition_render_plan(project([selected], aspect_ratio="9:16"))
        self.assertEqual(plan.video_clips[0]["asset_id"], "generated")
        self.assertEqual((plan.aspect_ratio, plan.fps), ("9:16", 30))
        with self.assertRaisesRegex(RuntimeError, "尚未选择素材"):
            compile_composition_render_plan(project([shot("empty", 0, None)]))

    def test_output_dimensions_and_frontend_adjustment_semantics(self):
        self.assertEqual(_target_dimensions("1080p", "16:9"), (1920, 1080))
        self.assertEqual(_target_dimensions("1080p", "9:16"), (1080, 1920))
        self.assertEqual(_target_dimensions("720p", "1:1"), (720, 720))
        self.assertEqual(_target_dimensions("480p", "4:3"), (640, 480))
        graph = _video_filter(
            {"adjust": {}, "transform": {}, "motion": {}, "transition": {}, "fps": 25},
            1280, 720, 2.0,
        )
        self.assertIn("eq=brightness=0.000000:contrast=1.000000:saturation=1.000000", graph)

    def test_project_color_grade_is_inherited_and_shot_can_override(self):
        inherited = shot("shot-1", 0, "video-1", adjust={"mode": "inherit"})
        overridden = shot("shot-2", 1, "video-2", adjust={"mode": "override", "brightness": 18})
        plan = compile_composition_render_plan(project(
            [inherited, overridden],
            visual_settings={"colorGrade": {"filterPreset": "cinematic", "brightness": 4}},
        ))
        self.assertEqual(
            plan.video_clips[0]["adjust"],
            {"filterPreset": "cinematic", "brightness": 4},
        )
        self.assertEqual(
            plan.video_clips[1]["adjust"],
            {"brightness": 18},
        )

    @patch.object(export_tasks, "_run_command")
    @patch.object(export_tasks, "_render_subtitle_image")
    def test_subtitle_position_is_compiled_into_overlay(self, _render_image, run_command):
        export_tasks._burn_subtitles(
            "ffmpeg", "/tmp/source.mp4",
            [
                {"text": "顶部", "start": 0, "duration": 1, "settings": {"position": "top"}},
                {"text": "居中", "start": 1, "duration": 1, "settings": {"position": "center"}},
            ],
            "/tmp/output.mp4", "/tmp", 1280, 720, 2, "/tmp/font.ttf",
        )
        command = run_command.call_args.args[0]
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("y='30'", graph)
        self.assertIn("y='(main_h-overlay_h)/2'", graph)


class ExportDispatchParameterTests(unittest.IsolatedAsyncioTestCase):
    @patch.object(generate, "dispatch_project_task", new_callable=AsyncMock)
    async def test_initial_dispatch_keeps_export_aspect_ratio(self, dispatch):
        dispatch.return_value = ns(id="celery-task")
        job = ns(
            type="导出", id="job-1",
            payload={
                "format": "mp4", "resolution": "1080p", "aspect_ratio": "9:16",
            },
        )
        await generate._dispatch_job(object(), ns(id="project-1"), job)
        args = dispatch.await_args.args
        self.assertEqual(args[-3:], ("mp4", "1080p", "9:16"))

    @patch.object(jobs, "dispatch_project_task", new_callable=AsyncMock)
    async def test_retry_dispatch_keeps_export_aspect_ratio(self, dispatch):
        dispatch.return_value = ns(id="celery-task")
        job = ns(
            type="导出", id="job-1", owner_id="owner-1", project_id="project-1",
            payload={
                "project_id": "project-1", "format": "mp4",
                "resolution": "4k", "aspect_ratio": "1:1",
            },
        )
        await jobs._dispatch_replay(object(), job)
        args = dispatch.await_args.args
        self.assertEqual(args[-3:], ("mp4", "4k", "1:1"))

    @patch.object(generate, "dispatch_project_task", new_callable=AsyncMock)
    async def test_initial_dispatch_supports_project_script_generation(self, dispatch):
        dispatch.return_value = ns(id="celery-task")
        job = ns(type="AI 脚本生成", id="job-1", payload={"project_id": "project-1"})
        await generate._dispatch_job(object(), ns(id="project-1"), job)
        args = dispatch.await_args.args
        self.assertEqual(args[-2:], ("project-1", "job-1"))

    @patch.object(jobs, "dispatch_project_task", new_callable=AsyncMock)
    async def test_retry_dispatch_supports_project_script_generation(self, dispatch):
        dispatch.return_value = ns(id="celery-task")
        job = ns(
            type="AI 脚本生成", id="job-1", owner_id="owner-1", project_id="project-1",
            payload={"project_id": "project-1", "prompt": "生成脚本"},
        )
        await jobs._dispatch_replay(object(), job)
        args = dispatch.await_args.args
        self.assertEqual(args[-2:], ("project-1", "job-1"))

    @patch.object(jobs, "dispatch_project_task", new_callable=AsyncMock)
    async def test_retry_dispatch_supports_project_voiceover_generation(self, dispatch):
        dispatch.return_value = ns(id="celery-task")
        job = ns(
            type="AI 配音生成", id="job-voice", owner_id="owner-1",
            project_id="project-1", payload={"project_id": "project-1"},
        )
        await jobs._dispatch_replay(object(), job)
        args = dispatch.await_args.args
        self.assertEqual(args[-2:], ("job-voice", "project-1"))


class ExportJobMetadataTests(unittest.TestCase):
    def test_export_metadata_is_derived_without_exposing_payload(self):
        job = JobOut(
            id="job-1",
            owner_id="owner-1",
            project_id="project-1",
            name="导出主成片",
            type="导出",
            status="SUCCEEDED",
            stage="完成",
            stages=["准备素材", "渲染", "上传结果"],
            stage_index=2,
            progress=100,
            detail="导出完成",
            eta="",
            logs=[],
            result_detail="",
            is_simulated=False,
            payload={
                "project_id": "project-1",
                "format": "mp4",
                "resolution": "4k",
                "aspect_ratio": "9:16",
                "base_revision": 7,
            },
        )

        serialized = job.model_dump(mode="json")
        self.assertEqual(
            serialized["export_metadata"],
            {"format": "mp4", "resolution": "4k", "aspect_ratio": "9:16"},
        )
        self.assertNotIn("payload", serialized)

    def test_description_review_is_derived_without_exposing_generic_payload(self):
        job = JobOut(
            id="job-review",
            owner_id="owner-1",
            project_id="project-1",
            subject_type="shot",
            subject_id="shot-1",
            name="AI 完善分镜",
            type="AI 分镜完善",
            status="SUCCEEDED",
            stage="等待确认",
            stages=["完善描述", "等待确认"],
            stage_index=1,
            progress=100,
            detail="已生成 1 条镜头描述建议",
            eta="",
            logs=[],
            result_detail="AI 建议尚未修改项目",
            is_simulated=False,
            payload={
                "script_id": "script-1",
                "secret_internal_value": "must-not-leak",
                "review_proposal": {
                    "type": "shot_description",
                    "status": "pending",
                    "base_revision": 7,
                    "items": [{
                        "shot_id": "shot-1",
                        "original_description": "原描述",
                        "proposed_description": "AI 建议",
                    }],
                },
            },
        )

        serialized = job.model_dump(mode="json")
        self.assertEqual(serialized["review_proposal"]["status"], "pending")
        self.assertEqual(
            serialized["review_proposal"]["items"][0]["proposed_description"],
            "AI 建议",
        )
        self.assertNotIn("payload", serialized)


class GeneratedScriptContractTests(unittest.TestCase):
    def test_generated_script_is_normalized_to_exact_target_duration(self):
        result = normalize_generated_script(
            """```json
            {"scenes":[
              {"outline":"开场","narration":"进入现场","intent":"建立氛围","shots":[
                {"description":"会场全景，缓慢推进","duration_seconds":2},
                {"description":"产品灯光亮起，中景","duration_seconds":4}
              ]},
              {"outline":"收束","narration":"未来已经到来","shots":[
                {"description":"品牌标志定格","duration_seconds":2}
              ]}
            ]}
            ```""",
            60,
        )
        shots = [shot for scene in result for shot in scene["shots"]]
        self.assertEqual(sum(shot["duration_ms"] for shot in shots), 60_000)
        self.assertEqual([scene["outline"] for scene in result], ["开场", "收束"])
        self.assertEqual(result[0]["narration_text"], "进入现场")
        self.assertEqual(
            sum(scene["estimated_duration_ms"] for scene in result),
            60_000,
        )

    def test_generated_scene_without_shots_gets_an_editable_fallback_shot(self):
        result = normalize_generated_script(
            '[{"outline":"结尾","intent":"品牌愿景"}]',
            30,
        )
        self.assertEqual(result[0]["shots"][0]["description"], "品牌愿景")
        self.assertEqual(result[0]["shots"][0]["duration_ms"], 30_000)

    def test_invalid_generated_script_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "合法的场景数组"):
            normalize_generated_script('{"scenes":[]}', 60)


if __name__ == "__main__":
    unittest.main()
