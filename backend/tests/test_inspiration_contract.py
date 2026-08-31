import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import ValidationError

from app.api.assets import _asset_content_types, _asset_source_category
from app.api.inspiration import _task_out
from app.models.inspiration import InspirationRun, InspirationTask
from app.schemas.inspiration import InspirationRunOut, InspirationTaskCreate
from app.services.inspiration_schedule import next_inspiration_run
from app.services.inspiration_extraction import compare_source_states, extract_source_state
from app.services.web_search import _bing_freshness_filter, parse_bing_rss
from app.tasks.inspiration_tasks import _generate_normalized_result, _normalize_generated_content


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

    def test_topic_discovery_can_use_the_open_web_without_urls(self):
        task = InspirationTaskCreate(
            name="全网选题",
            task_type="topic-recommendation",
            topic_brief="AI 视频创作",
            sources=[],
        )
        self.assertEqual(task.discovery_config.source_strategy, "web")
        self.assertEqual(task.sources, [])

    def test_zero_source_topic_task_can_be_serialized_without_lazy_loading(self):
        task = InspirationTask(
            id="inspiration-task-test",
            owner_id="user-1",
            name="全网选题",
            task_type="topic-recommendation",
            topic_brief="AI 视频创作",
            topic_count=5,
            discovery_config={"source_strategy": "web", "monitor_brief": "", "search_recency_days": 7},
            schedule={"type": "manual", "time": "09:00", "weekday": 1, "time_zone": "Asia/Shanghai"},
            enabled=True,
            created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
            sources=[],
        )
        output = _task_out(task)
        self.assertEqual(output.sources, [])

    def test_new_run_can_be_serialized_without_lazy_loading_results(self):
        run = InspirationRun(
            id="inspiration-run-test",
            task_id="inspiration-task-test",
            status="QUEUED",
            metrics={},
            created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
            results=[],
        )
        output = InspirationRunOut.model_validate(run)
        self.assertEqual(output.results, [])

    def test_user_sites_become_preferred_when_strategy_was_web(self):
        task = InspirationTaskCreate(
            name="优先官网",
            task_type="topic-recommendation",
            topic_brief="AI 视频创作",
            sources=[{"url": "https://example.com/blog/"}],
        )
        self.assertEqual(task.discovery_config.source_strategy, "preferred")

    def test_link_monitor_requires_at_least_one_url(self):
        with self.assertRaises(ValidationError):
            InspirationTaskCreate(
                name="来源监控",
                task_type="link-update",
                sources=[],
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
            [
                {"url": "https://example.com/news", "content": "新版本发布"},
                {"url": "https://example.com/unused", "content": "没有被选题引用的候选"},
            ],
            task_name="每日选题",
            topic_count=1,
        )
        self.assertEqual(title, "本周选题")
        self.assertEqual(summary, "摘要")
        self.assertEqual(content["topics"][0]["references"][0]["url"], "https://example.com/news")
        self.assertEqual(len(content["topics"][0]["references"]), 1)
        self.assertEqual(citations[0]["url"], "https://example.com/news")
        self.assertEqual(len(citations), 1)

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

    def test_topic_result_rejects_topics_without_real_references(self):
        with self.assertRaisesRegex(ValueError, "有真实引用"):
            _normalize_generated_content(
                "topic-recommendation",
                {"topics": [{"title": "没有引用", "summary": "不应自动补引用"}]},
                [{"url": "https://example.com/news", "content": "内容"}],
                task_name="每日选题",
                topic_count=1,
            )


class InspirationExtractionTests(unittest.TestCase):
    def test_rss_detects_only_new_entries(self):
        first = extract_source_state(
            "https://example.com/feed.xml",
            "<rss><channel><title>更新</title><item><title>A</title><link>https://example.com/a</link></item></channel></rss>",
            "application/rss+xml",
            "rss",
        )
        second = extract_source_state(
            "https://example.com/feed.xml",
            "<rss><channel><title>更新</title><item><title>B</title><link>https://example.com/b</link></item><item><title>A</title><link>https://example.com/a</link></item></channel></rss>",
            "application/rss+xml",
            "rss",
        )
        diff = compare_source_states(first, second)
        self.assertEqual(diff["status"], "CHANGED")
        self.assertEqual([item["title"] for item in diff["evidence"]], ["B"])

    def test_homepage_reordering_is_not_an_update(self):
        def homepage(order: list[int]) -> str:
            links = "".join(
                f'<a href="/news/{index}">这是第 {index} 条足够长的新闻标题</a>'
                for index in order
            )
            return f"<html><head><title>新闻站</title></head><body>{links}</body></html>"

        first = extract_source_state("https://example.com/", homepage(list(range(10))), "text/html")
        second = extract_source_state("https://example.com/", homepage(list(reversed(range(10)))), "text/html")
        self.assertEqual(first["mode"], "listing")
        self.assertEqual(compare_source_states(first, second)["status"], "UNCHANGED")

    def test_first_monitoring_fetch_only_creates_a_baseline(self):
        current = extract_source_state(
            "https://example.com/article",
            "<main><h1>产品更新</h1><p>这是一段足够长的正文，用于建立首次监控基线。</p><p>另一段稳定正文内容。</p></main>",
            "text/html",
        )
        self.assertEqual(compare_source_states(None, current)["status"], "BASELINE_CREATED")

    def test_bing_rss_parser_filters_insecure_results(self):
        results = parse_bing_rss(
            "<rss><channel><item><title>安全结果</title><link>https://example.com/a</link></item><item><title>不安全</title><link>http://example.com/b</link></item></channel></rss>",
            10,
        )
        self.assertEqual([item.url for item in results], ["https://example.com/a"])

    def test_bing_freshness_filter_uses_supported_time_buckets(self):
        self.assertEqual(_bing_freshness_filter(1), 'ex1:"ez1"')
        self.assertEqual(_bing_freshness_filter(7), 'ex1:"ez2"')
        self.assertEqual(_bing_freshness_filter(14), 'ex1:"ez3"')
        self.assertIsNone(_bing_freshness_filter(None))


class InspirationGenerationRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_model_json_is_retried_once(self):
        responses = iter([
            '{"topics":[{"title":"不完整"}',
            '{"title":"本周选题","summary":"摘要","topics":[{"title":"工具变化","angle":"效率","summary":"工作流更新","why_now":"刚刚发布","hook":"先看变化","reference_urls":["https://example.com/news"]}]}',
        ])

        async def fake_generate_text(**_kwargs):
            return next(responses)

        task = SimpleNamespace(
            task_type="topic-recommendation",
            topic_count=1,
            name="每日选题",
            topic_brief="AI 视频创作",
        )
        title, _summary, content, _citations = await _generate_normalized_result(
            task,
            [{"url": "https://example.com/news", "content": "新版本发布"}],
            fake_generate_text,
            system_prompt="只输出 JSON",
            temperature=0.4,
            max_tokens=1000,
        )
        self.assertEqual(title, "本周选题")
        self.assertEqual(content["topics"][0]["references"][0]["url"], "https://example.com/news")


if __name__ == "__main__":
    unittest.main()
