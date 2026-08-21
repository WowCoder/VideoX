import json
import unittest

from app.services.ai_provider import normalize_visual_recognition
from app.services.creation_preview import normalize_asset_preview, normalize_script_preview


class ScriptCreationPreviewTests(unittest.TestCase):
    def test_normalizes_multiple_shots_and_allocates_exact_target_duration(self):
        result = normalize_script_preview(json.dumps({
            "title": "真实脚本",
            "summary": "从问题推进到答案",
            "scenes": [
                {
                    "title": "开场",
                    "narration": "一个问题正在发生。",
                    "visual": "进入真实工作现场",
                    "shots": [
                        {"description": "现场全景，缓慢推进", "duration_seconds": 2},
                        {"description": "人物手部特写", "duration_seconds": 1},
                    ],
                },
                {
                    "title": "回答",
                    "narration": "答案来自具体行动。",
                    "visual": "展示解决过程",
                    "shots": [{"description": "中景跟随人物完成操作", "duration_seconds": 3}],
                },
            ],
        }, ensure_ascii=False), 30)

        shots = [shot for scene in result["scenes"] for shot in scene["shots"]]
        self.assertEqual(len(shots), 3)
        self.assertEqual(sum(shot["duration_ms"] for shot in shots), 30_000)
        self.assertEqual(
            sum(scene["duration_ms"] for scene in result["scenes"]),
            30_000,
        )

    def test_rejects_non_json_and_empty_scenes(self):
        with self.assertRaisesRegex(RuntimeError, "合法 JSON"):
            normalize_script_preview("不是 JSON", 60)
        with self.assertRaisesRegex(RuntimeError, "没有生成可用"):
            normalize_script_preview('{"scenes": []}', 60)


class AssetCreationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.available = {
            "segment-1": {
                "asset_id": "asset-1",
                "start_ms": 2_000,
                "end_ms": 12_000,
                "title": "工作现场",
                "summary": "人物正在操作设备",
            }
        }

    def test_preserves_verified_asset_segment_and_source_range(self):
        result = normalize_asset_preview(json.dumps({
            "title": "素材影片",
            "scenes": [{
                "title": "行动",
                "narration": "行动让变化发生。",
                "visual": "人物操作设备",
                "shots": [{
                    "segment_id": "segment-1",
                    "description": "使用人物操作设备的中景",
                    "duration_seconds": 4,
                }],
            }],
        }, ensure_ascii=False), self.available)

        shot = result["scenes"][0]["shots"][0]
        self.assertEqual(shot["asset_id"], "asset-1")
        self.assertEqual(shot["segment_id"], "segment-1")
        self.assertEqual((shot["source_start_ms"], shot["source_end_ms"]), (2_000, 6_000))

    def test_rejects_invented_and_duplicate_segment_ids(self):
        invented = '{"scenes":[{"narration":"旁白","shots":[{"segment_id":"invented","description":"镜头"}]}]}'
        with self.assertRaisesRegex(RuntimeError, "不可用"):
            normalize_asset_preview(invented, self.available)

        duplicate = '{"scenes":[{"narration":"旁白","shots":[{"segment_id":"segment-1","description":"镜头一"},{"segment_id":"segment-1","description":"镜头二"}]}]}'
        with self.assertRaisesRegex(RuntimeError, "重复使用"):
            normalize_asset_preview(duplicate, self.available)


class VisualRecognitionNormalizationTests(unittest.TestCase):
    def test_normalizes_entities_roles_quality_and_confidence(self):
        result = normalize_visual_recognition({
            "summary": "展厅中一名人物正在演示机器人。",
            "spaces": [{"label": "展厅", "confidence": 1.4}],
            "people": [{"label": "人物 01", "role": "演示人员", "confidence": 0.83}],
            "objects": ["机器人", "机器人"],
            "actions": [{"label": "演示", "confidence": -0.2}],
            "shot": {"scale": "中景", "camera_motion": "缓慢推进"},
            "quality": {"sharpness": 1.2, "usable_score": 108},
            "tags": ["科技", "科技", "展厅"],
        })

        self.assertEqual(result["spaces"][0]["confidence"], 1.0)
        self.assertEqual(result["people"][0]["role"], "演示人员")
        self.assertEqual(len(result["objects"]), 1)
        self.assertEqual(result["actions"][0]["confidence"], 0.0)
        self.assertEqual(result["quality"], {"sharpness": 1.0, "usable_score": 100.0})
        self.assertEqual(result["tags"], ["科技", "展厅"])


if __name__ == "__main__":
    unittest.main()
