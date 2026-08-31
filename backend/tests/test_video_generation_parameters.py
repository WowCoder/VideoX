from types import SimpleNamespace
import unittest

from app.api.generate import _validated_video_generation
from app.schemas.project import ScopeSelection


def _asset(asset_id: str, media_type: str = "image"):
    return SimpleNamespace(
        id=asset_id,
        owner_id="user-1",
        deleted_at=None,
        status="ready",
        processing_status="ready",
        media_type=media_type,
        file_path=f"projects/{asset_id}.png",
    )


def _project(*assets):
    return SimpleNamespace(
        asset_links=[SimpleNamespace(asset=asset) for asset in assets]
    )


class VideoGenerationParameterTests(unittest.TestCase):
    def test_reference_mode_keeps_ordered_image_provenance(self):
        project = _project(_asset("image-1"), _asset("image-2"))

        result = _validated_video_generation(
            project,
            "user-1",
            ScopeSelection(type="shot", shot_ids=["shot-1"]),
            ["shot-1"],
            {
                "generation_mode": "reference",
                "duration_seconds": 8,
                "reference_image_asset_ids": ["image-2", "image-1"],
            },
        )

        self.assertEqual(result["mode"], "reference")
        self.assertEqual(result["duration_seconds"], 8)
        self.assertEqual(result["reference_assets"], [
            {"asset_id": "image-2", "role": "reference", "ordinal": 1},
            {"asset_id": "image-1", "role": "reference", "ordinal": 2},
        ])

    def test_keyframe_mode_requires_single_shot_scope(self):
        with self.assertRaisesRegex(Exception, "暂时只支持单个镜头"):
            _validated_video_generation(
                _project(_asset("image-1")),
                "user-1",
                ScopeSelection(type="scene", scene_ids=["scene-1"]),
                ["shot-1", "shot-2"],
                {
                    "generation_mode": "keyframe",
                    "first_frame_asset_id": "image-1",
                },
            )

    def test_video_asset_cannot_be_sent_as_flash_image_reference(self):
        with self.assertRaisesRegex(Exception, "处理完成的图片"):
            _validated_video_generation(
                _project(_asset("video-1", media_type="video")),
                "user-1",
                ScopeSelection(type="shot", shot_ids=["shot-1"]),
                ["shot-1"],
                {
                    "generation_mode": "reference",
                    "reference_image_asset_ids": ["video-1"],
                },
            )

    def test_reference_mode_rejects_more_than_five_images_before_dispatch(self):
        with self.assertRaisesRegex(Exception, "最多支持 5 张参考图片"):
            _validated_video_generation(
                _project(*[_asset(f"image-{index}") for index in range(6)]),
                "user-1",
                ScopeSelection(type="shot", shot_ids=["shot-1"]),
                ["shot-1"],
                {
                    "generation_mode": "reference",
                    "reference_image_asset_ids": [f"image-{index}" for index in range(6)],
                },
            )

    def test_flash_duration_is_validated_before_job_creation(self):
        with self.assertRaisesRegex(Exception, "4–12 秒"):
            _validated_video_generation(
                _project(),
                "user-1",
                ScopeSelection(type="shot", shot_ids=["shot-1"]),
                ["shot-1"],
                {"generation_mode": "text", "duration_seconds": 3},
            )


if __name__ == "__main__":
    unittest.main()
