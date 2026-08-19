import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import ValidationError

from app.api.assets import _asset_content_types, _asset_source_category
from app.schemas.inspiration import InspirationTaskCreate
from app.services.inspiration_schedule import next_inspiration_run
from app.tasks.inspiration_tasks import _normalize_generated_content


class AssetClassificationTests(unittest.TestCase):
    def test_asset_and_segment_recognition_are_combined(self):
        asset = SimpleNamespace(
            recognition={"locations": ["上海"]},
            tags=["产品", "人物"],
            segments=[SimpleNamespace(recognition={"actions": ["奔跑"]})],
            source_type="ai_generated",
        )
        self.assertEqual(_asset_content_types(asset), ["scene", "role", "object", "event"])
        self.assertEqual(_asset_source_category(asset), "ai")

    def test_uploaded_assets_are_non_ai_by_default(self):
        asset = SimpleNamespace(source_type="upload")
        self.assertEqual(_asset_source_category(asset), "non-ai")


class InspirationContractTests(unittest.TestCase):
    def test_topic_task_requires_a_brief(self):
        with self.assertRaises(ValidationError):
            InspirationTaskCreate(
                name="每日选题",
                task_type="topic-recommendation",
                sources=[{"url": "https://example.com/news"}],
            )

    def test_link_task_discards_topic_only_fields(self):
        task = InspirationTaskCreate(
            name="产品动态",
            task_type="link-update",
            topic_brief="不应保存",
            topic_count=8,
            sources=[{"url": "https://example.com/changelog"}],
        )
        self.assertEqual(task.topic_brief, "")
        self.assertIsNone(task.topic_count)

    def test_daily_and_manual_schedule(self):
        # 2026-08-18 00:00 UTC is 08:00 in Asia/Shanghai.
        after = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
        next_run = next_inspiration_run(
            {"type": "daily", "time": "09:00", "weekday": 1, "time_zone": "Asia/Shanghai"},
            after,
        )
        self.assertEqual(next_run, datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc))
        self.assertIsNone(next_inspiration_run(
            {"type": "manual", "time": "09:00", "weekday": 1, "time_zone": "Asia/Shanghai"},
            after,
        ))

    def test_topic_results_only_keep_traceable_references(self):
        title, summary, content, citations = _normalize_generated_content(
            "topic-recommendation",
            {
                "title": "本周选题",
                "summary": "摘要",
                "topics": [{
                    "title": "工具变化",
                    "angle": "效率",
                    "summary": "从效率变化切入",
                    "reference_urls": ["https://example.com/news", "https://untrusted.example/"],
                }],
            },
            [{"url": "https://example.com/news", "content": "新版本发布"}],
            task_name="每日选题",
            topic_count=1,
        )
        self.assertEqual(title, "本周选题")
        self.assertEqual(summary, "摘要")
        self.assertEqual(content["topics"][0]["references"][0]["url"], "https://example.com/news")
        self.assertEqual(len(content["topics"][0]["references"]), 1)
        self.assertEqual(citations[0]["url"], "https://example.com/news")

    def test_link_results_preserve_every_changed_source(self):
        _, _, content, _ = _normalize_generated_content(
            "link-update",
            {"updates": [{"url": "https://a.example/news", "title": "A 更新", "summary": "A 摘要"}]},
            [
                {"url": "https://a.example/news", "content": "A"},
                {"url": "https://b.example/news", "content": "B"},
            ],
            task_name="产品动态",
            topic_count=None,
        )
        self.assertEqual([item["url"] for item in content["updates"]], [
            "https://a.example/news",
            "https://b.example/news",
        ])

    def test_topic_result_rejects_an_incomplete_model_response(self):
        with self.assertRaisesRegex(ValueError, "预期 2 个"):
            _normalize_generated_content(
                "topic-recommendation",
                {"topics": [{"title": "只有一个", "summary": "不满足数量"}]},
                [{"url": "https://example.com/news", "content": "内容"}],
                task_name="每日选题",
                topic_count=2,
            )


if __name__ == "__main__":
    unittest.main()
