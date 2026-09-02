import unittest
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from openai import AsyncOpenAI

from app.services import ai_provider
from app.tasks.async_runner import run_async


class FakeResponse:
    def __init__(
        self,
        payload,
        status_error: Exception | None = None,
        status_code: int = 200,
        headers: dict | None = None,
    ):
        self.payload = payload
        self.status_error = status_error
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, response, *args, **kwargs):
        del args, kwargs
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        del args, kwargs
        return self.response

    async def get(self, *args, **kwargs):
        del args, kwargs
        return self.response


class RecordingAsyncClient:
    def __init__(self, responses, calls, *args, **kwargs):
        del args, kwargs
        self.responses = responses
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class FakeRateLimitRedis:
    def __init__(self, acquisitions, remaining_ms=0):
        self.acquisitions = list(acquisitions)
        self.remaining_ms = remaining_ms
        self.set_calls = []
        self.closed = False

    async def set(self, key, value, **kwargs):
        self.set_calls.append((key, value, kwargs))
        return self.acquisitions.pop(0)

    async def pttl(self, key):
        del key
        return self.remaining_ms

    async def aclose(self):
        self.closed = True


class LocalEmbeddingProviderTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return SimpleNamespace(
            ai_embedding_provider="local",
            local_ai_timeout_seconds=30,
            local_embedding_url="http://embedding:8000",
            local_ai_api_key="test-token",
            ai_embedding_model="BAAI/bge-m3",
            ai_embedding_dimensions=1024,
        )

    async def test_accepts_real_1024_dimension_response(self):
        response = FakeResponse({"data": [{"embedding": [0.1] * 1024}]})
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: FakeAsyncClient(response, *args, **kwargs),
        ):
            vector = await ai_provider.generate_embedding("真实素材文本")
        self.assertEqual(len(vector), 1024)

    async def test_rejects_wrong_dimension_instead_of_padding(self):
        response = FakeResponse({"data": [{"embedding": [0.1] * 768}]})
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: FakeAsyncClient(response, *args, **kwargs),
        ):
            with self.assertRaisesRegex(RuntimeError, "维度异常"):
                await ai_provider.generate_embedding("真实素材文本")


class OpenAIClientLifecycleTests(unittest.TestCase):
    def test_generate_text_closes_real_client_before_celery_loop_ends(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "agnes-2.5-flash",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "OK"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncOpenAI(
            api_key="test-key",
            base_url="https://agnes.example/v1",
            http_client=http_client,
        )
        selected = SimpleNamespace(
            ai_text_provider="agnes",
            agnes_text_model="agnes-2.5-flash",
        )
        with patch.object(ai_provider, "settings", selected), patch.object(
            ai_provider,
            "_agnes_client",
            return_value=client,
        ):
            result = run_async(ai_provider.generate_text("只回复 OK"))

        self.assertEqual(result, "OK")
        self.assertTrue(http_client.is_closed)


class DashScopeGenerationProviderTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return SimpleNamespace(
            ai_image_provider="dashscope",
            ai_image_model="wanx2.1-t2i-turbo",
            ai_text_to_video_provider="dashscope",
            ai_text_to_video_model="wanx2.1-t2v-turbo",
            ai_image_to_video_provider="dashscope",
            ai_image_to_video_model="wan2.1-i2v-turbo",
            ai_effect_video_provider="dashscope",
            ai_effect_video_model="wan2.1-i2v-turbo",
            ai_video_resolution="720P",
            ai_video_duration_seconds=5,
            ai_video_prompt_extend=True,
            ai_video_watermark=False,
            dashscope_api_key="test-key",
            dashscope_api_url="https://dashscope.aliyuncs.com/api/v1",
            dashscope_poll_interval_seconds=0.2,
            dashscope_generation_timeout_seconds=30,
            video_poll_interval_seconds=10,
            has_dashscope=True,
        )

    async def test_image_uses_native_async_endpoint_and_polls_task(self):
        calls = []
        responses = [
            FakeResponse({"output": {"task_id": "task-1"}}),
            FakeResponse({"output": {"task_status": "RUNNING"}}),
            FakeResponse({"output": {"task_status": "SUCCEEDED", "results": [{"url": "https://example.aliyuncs.com/image.png"}]}}),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(responses, calls, *args, **kwargs),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            url = await ai_provider.generate_image("真实分镜", size="1024*576")

        self.assertEqual(url, "https://example.aliyuncs.com/image.png")
        self.assertEqual(
            calls[0][1],
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        )
        self.assertEqual(calls[0][2]["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(calls[0][2]["json"]["parameters"]["size"], "1280*720")
        self.assertEqual(
            calls[1][1],
            "https://dashscope.aliyuncs.com/api/v1/tasks/task-1",
        )

    async def test_effect_uploads_canvas_to_temporary_oss_and_uses_media_protocol(self):
        calls = []
        responses = [
            FakeResponse({
                "data": {
                    "upload_host": "https://temporary-oss.example.com",
                    "upload_dir": "dashscope-instant/user-1",
                    "oss_access_key_id": "access-id",
                    "signature": "signature",
                    "policy": "policy",
                }
            }),
            FakeResponse({}),
            FakeResponse({"output": {"task_id": "effect-task"}}),
        ]
        sketch = "data:image/png;base64," + base64.b64encode(
            b"\x89PNG\r\n\x1a\nreal-png-bytes"
        ).decode()
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(responses, calls, *args, **kwargs),
        ):
            task_id = await ai_provider.generate_effect_video(
                "箭头从左向右移动",
                sketch_data=sketch,
            )

        self.assertEqual(task_id, "effect-task")
        self.assertEqual(calls[0][0], "GET")
        self.assertTrue(calls[0][1].endswith("/uploads"))
        self.assertEqual(calls[0][2]["params"]["model"], "wan2.1-i2v-turbo")
        self.assertEqual(calls[1][1], "https://temporary-oss.example.com")
        submit = calls[2][2]
        media = submit["json"]["input"]["media"][0]
        self.assertEqual(media["type"], "first_frame")
        self.assertTrue(media["url"].startswith("oss://dashscope-instant/user-1/"))
        self.assertEqual(submit["headers"]["X-DashScope-OssResourceResolve"], "enable")

    async def test_video_uses_native_async_endpoint(self):
        calls = []
        responses = [
            FakeResponse({"output": {"task_id": "video-task"}}),
            FakeResponse({
                "output": {
                    "task_status": "SUCCEEDED",
                    "video_url": "https://example.aliyuncs.com/video.mp4",
                }
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(responses, calls, *args, **kwargs),
        ), patch.object(
            ai_provider,
            "_prepare_agnes_video_first_frame",
            new_callable=AsyncMock,
        ) as agnes_prepare, patch.object(
            ai_provider.asyncio, "sleep", new_callable=AsyncMock
        ):
            url = await ai_provider.generate_video("镜头运动", image_url="https://example.com/frame.png")

        self.assertEqual(url, "https://example.aliyuncs.com/video.mp4")
        self.assertEqual(
            calls[0][1],
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
        )
        self.assertEqual(calls[0][2]["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(
            calls[0][2]["json"]["input"]["media"],
            [{"type": "first_frame", "url": "https://example.com/frame.png"}],
        )
        self.assertNotIn("img_url", calls[0][2]["json"]["input"])
        self.assertEqual(
            calls[1][1],
            "https://dashscope.aliyuncs.com/api/v1/tasks/video-task",
        )
        agnes_prepare.assert_not_awaited()

    async def test_video_submit_returns_provider_task_without_polling(self):
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider,
            "_submit_video_task",
            new_callable=AsyncMock,
            return_value="video-task",
        ) as submit, patch.object(
            ai_provider,
            "query_video_task",
            new_callable=AsyncMock,
        ) as query:
            result = await ai_provider.submit_video_generation("镜头运动")

        self.assertEqual(result["provider"], "dashscope")
        self.assertEqual(result["task_id"], "video-task")
        submit.assert_awaited_once()
        query.assert_not_awaited()

    async def test_dashscope_single_poll_maps_pending_success_and_failure(self):
        pending = {"output": {"task_status": "RUNNING"}}
        succeeded = {
            "output": {
                "task_status": "SUCCEEDED",
                "video_url": "https://example.aliyuncs.com/video.mp4",
            }
        }
        failed = {
            "output": {
                "task_status": "FAILED",
                "code": "QuotaExhausted",
                "message": "No quota left",
            }
        }
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider,
            "query_video_task",
            new_callable=AsyncMock,
            side_effect=[pending, succeeded, failed],
        ):
            self.assertEqual(
                (await ai_provider.poll_video_generation("dashscope", "task"))["state"],
                "pending",
            )
            success = await ai_provider.poll_video_generation("dashscope", "task")
            failure = await ai_provider.poll_video_generation("dashscope", "task")

        self.assertEqual(success["state"], "succeeded")
        self.assertEqual(success["result_url"], "https://example.aliyuncs.com/video.mp4")
        self.assertEqual(failure["state"], "failed")
        self.assertIn("QuotaExhausted", failure["error"])

    async def test_video_content_review_failure_is_actionable_chinese(self):
        calls = []
        request = httpx.Request("POST", "https://dashscope.aliyuncs.com/api/v1/video")
        response = httpx.Response(400, request=request)
        responses = [
            FakeResponse(
                {
                    "output": {
                        "code": "DataInspectionFailed",
                        "message": (
                            "Green net check failed for image (input): "
                            "Input data may contain inappropriate content."
                        ),
                        "request_id": "review-request-1",
                    }
                },
                httpx.HTTPStatusError(
                    "content review failed",
                    request=request,
                    response=response,
                ),
            )
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "首帧图片未通过服务商安全审核") as error:
                await ai_provider.generate_video(
                    "缓慢推进",
                    image_url="https://example.com/frame.png",
                )

        self.assertIn("更换或重新生成首帧图片", str(error.exception))
        self.assertIn("审核参考号：review-request-1", str(error.exception))
        self.assertNotIn("Green net check failed", str(error.exception))

    def test_non_review_video_failure_keeps_provider_diagnostics(self):
        message = ai_provider.video_task_failure_message(
            {
                "output": {
                    "code": "QuotaExhausted",
                    "message": "No quota left",
                    "request_id": "request-2",
                }
            },
            "AI 视频生成任务失败",
        )

        self.assertIn("QuotaExhausted", message)
        self.assertIn("No quota left", message)
        self.assertIn("request_id=request-2", message)


class AgnesGenerationProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.real_submit_limiter = ai_provider._wait_for_agnes_video_submit_slot
        limiter_patch = patch.object(
            ai_provider,
            "_wait_for_agnes_video_submit_slot",
            new_callable=AsyncMock,
        )
        self.submit_limiter = limiter_patch.start()
        self.addCleanup(limiter_patch.stop)

    def settings(self):
        return SimpleNamespace(
            ai_image_provider="agnes",
            ai_text_to_video_provider="agnes",
            ai_image_to_video_provider="agnes",
            ai_video_duration_seconds=5,
            agnes_api_key="test-key",
            agnes_base_url="https://api.agnes-ai.cn/v1",
            agnes_image_model="agnes-image-2.1-flash",
            agnes_video_model="agnes-video-v2.0",
            agnes_poll_interval_seconds=0.2,
            agnes_generation_timeout_seconds=30,
            agnes_video_submit_interval_seconds=61,
            agnes_video_submit_max_attempts=4,
            agnes_video_submit_retry_seconds=0.2,
            has_agnes=True,
        )

    def flash_settings(self):
        selected = self.settings()
        selected.agnes_video_model = "agnes-video-2.5-flash"
        return selected

    async def test_flash_text_payload_and_poll_query(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "flash-text"}),
            FakeResponse({
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/flash-text.mp4"},
            }),
        ]
        with patch.object(ai_provider, "settings", self.flash_settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            url = await ai_provider.generate_video(
                "雨夜中的城市街道",
                duration=6,
                mode="text",
            )

        self.assertEqual(url, "https://output.agnes-ai.cn/flash-text.mp4")
        submit = calls[0][2]["json"]
        self.assertEqual(submit["model"], "agnes-video-2.5-flash")
        self.assertEqual(submit["mode"], "text")
        self.assertEqual(submit["seconds"], "6")
        self.assertEqual(submit["size"], "720P")
        self.assertNotIn("images", submit)
        self.assertTrue(calls[1][1].endswith("/agnesapi"))
        self.assertEqual(calls[1][2]["params"], {
            "video_id": "flash-text",
            "model_name": "agnes-video-2.5-flash",
        })

    async def test_flash_submit_returns_task_id_without_polling(self):
        calls = []
        responses = [FakeResponse({"video_id": "flash-submit"})]
        with patch.object(ai_provider, "settings", self.flash_settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            result = await ai_provider.submit_video_generation(
                "雨夜中的城市街道",
                duration=6,
                mode="text",
            )

        self.assertEqual(result["provider"], "agnes")
        self.assertEqual(result["task_id"], "flash-submit")
        self.assertTrue(result["uses_agnesapi_poll"])
        self.assertEqual([call[0] for call in calls], ["POST"])

    async def test_agnes_single_poll_maps_busy_success_and_failure(self):
        selected = self.flash_settings()
        selected.video_poll_interval_seconds = 10
        responses = [
            FakeResponse({}, status_code=429, headers={"Retry-After": "7"}),
            FakeResponse({
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/video.mp4"},
            }),
            FakeResponse({"status": "failed", "error": "generation rejected"}),
        ]
        calls = []
        with patch.object(ai_provider, "settings", selected), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            busy = await ai_provider.poll_video_generation(
                "agnes", "task", model="agnes-video-2.5-flash", uses_agnesapi_poll=True
            )
            success = await ai_provider.poll_video_generation(
                "agnes", "task", model="agnes-video-2.5-flash", uses_agnesapi_poll=True
            )
            failure = await ai_provider.poll_video_generation(
                "agnes", "task", model="agnes-video-2.5-flash", uses_agnesapi_poll=True
            )

        self.assertEqual(busy, {"state": "pending", "retry_after": 10})
        self.assertEqual(success["state"], "succeeded")
        self.assertEqual(success["result_url"], "https://output.agnes-ai.cn/video.mp4")
        self.assertEqual(failure, {"state": "failed", "error": "generation rejected"})

    async def test_flash_keyframe_payload_supports_first_and_last_frame(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "flash-keyframe"}),
            FakeResponse({
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/keyframe.mp4"},
            }),
        ]
        prepared = ["https://public.example.com/first.png", "https://public.example.com/last.png"]
        with patch.object(ai_provider, "settings", self.flash_settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(
            ai_provider,
            "_prepare_agnes_video_first_frame",
            new_callable=AsyncMock,
            side_effect=prepared,
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            await ai_provider.generate_video(
                "人物从室内走到室外",
                duration=8,
                mode="keyframe",
                first_frame_url="private/first.png",
                last_frame_url="private/last.png",
            )

        submit = calls[0][2]["json"]
        self.assertEqual(submit["mode"], "keyframe")
        self.assertEqual(submit["first_frame"], prepared[0])
        self.assertEqual(submit["last_frame"], prepared[1])

    async def test_flash_reference_payload_uses_up_to_five_images(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "flash-reference"}),
            FakeResponse({
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/reference.mp4"},
            }),
        ]
        prepared = [f"https://public.example.com/reference-{index}.png" for index in range(3)]
        with patch.object(ai_provider, "settings", self.flash_settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(
            ai_provider,
            "_prepare_agnes_video_first_frame",
            new_callable=AsyncMock,
            side_effect=prepared,
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            await ai_provider.generate_video(
                "保持人物和场景风格一致",
                duration=12,
                mode="reference",
                reference_image_urls=["private/one.png", "private/two.png", "private/three.png"],
            )

        submit = calls[0][2]["json"]
        self.assertEqual(submit["mode"], "reference")
        self.assertEqual(submit["images"], prepared)
        self.assertNotIn("videos", submit)

    def test_flash_reference_payload_rejects_more_than_five_images(self):
        with self.assertRaisesRegex(RuntimeError, "最多支持 5 张参考图片"):
            ai_provider._agnes_video_payload(
                "agnes-video-2.5-flash",
                "保持一致",
                "",
                5,
                "16:9",
                mode="reference",
                reference_images=[f"https://example.com/{index}.png" for index in range(6)],
            )

    def test_flash_duration_is_clamped_to_supported_range(self):
        short, _ = ai_provider._agnes_video_payload(
            "agnes-video-2.5-flash", "短镜头", "", 1, "16:9", mode="text"
        )
        long, _ = ai_provider._agnes_video_payload(
            "agnes-video-2.5-flash", "长镜头", "", 30, "16:9", mode="text"
        )
        self.assertEqual(short["seconds"], "4")
        self.assertEqual(long["seconds"], "12")

    async def test_video_submit_limiter_waits_for_shared_redis_slot(self):
        selected = self.settings()
        selected.redis_url = "redis://redis:6379/0"
        fake_redis = FakeRateLimitRedis([False, True], remaining_ms=1500)
        with patch.object(ai_provider, "settings", selected), patch(
            "redis.asyncio.from_url",
            return_value=fake_redis,
        ) as from_url, patch.object(
            ai_provider.asyncio,
            "sleep",
            new_callable=AsyncMock,
        ) as sleep:
            # setUp 默认隔离外部 Redis；此处直接调用保存的真实实现。
            await self.real_submit_limiter()

        from_url.assert_called_once_with(
            "redis://redis:6379/0",
            decode_responses=True,
        )
        self.assertEqual(len(fake_redis.set_calls), 2)
        first_key, _, first_options = fake_redis.set_calls[0]
        self.assertTrue(first_key.startswith("openvma:agnes-video-submit:"))
        self.assertEqual(first_options, {"nx": True, "px": 61000})
        sleep.assert_awaited_once_with(1.55)
        self.assertTrue(fake_redis.closed)

    async def test_text_uses_agnes_client_and_provider_model(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="AGNES_OK"))]
        )
        create = AsyncMock(return_value=completion)
        client = AsyncMock()
        client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        selected = self.settings()
        selected.ai_text_provider = "agnes"
        selected.agnes_text_model = "agnes-2.5-flash"
        with patch.object(ai_provider, "settings", selected), patch.object(
            ai_provider, "_agnes_client", return_value=client
        ) as client_factory:
            result = await ai_provider.generate_text("只回复 AGNES_OK")

        self.assertEqual(result, "AGNES_OK")
        client_factory.assert_called_once_with()
        self.assertEqual(create.await_args.kwargs["model"], "agnes-2.5-flash")
        client.__aenter__.assert_awaited_once_with()
        client.__aexit__.assert_awaited_once()

    async def test_text_closes_agnes_client_when_request_fails(self):
        create = AsyncMock(side_effect=RuntimeError("provider failed"))
        client = AsyncMock()
        client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        selected = self.settings()
        selected.ai_text_provider = "agnes"
        selected.agnes_text_model = "agnes-2.5-flash"
        with patch.object(ai_provider, "settings", selected), patch.object(
            ai_provider, "_agnes_client", return_value=client
        ):
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                await ai_provider.generate_text("测试失败后的客户端释放")

        client.__aenter__.assert_awaited_once_with()
        client.__aexit__.assert_awaited_once()

    async def test_image_uses_china_endpoint_and_maps_ratio(self):
        calls = []
        responses = [
            FakeResponse({"data": [{"url": "https://output.agnes-ai.cn/image.png"}]})
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            url = await ai_provider.generate_image("真实分镜", size="720*1280")

        self.assertEqual(url, "https://output.agnes-ai.cn/image.png")
        self.assertEqual(calls[0][1], "https://api.agnes-ai.cn/v1/images/generations")
        self.assertEqual(calls[0][2]["json"]["model"], "agnes-image-2.1-flash")
        self.assertEqual(calls[0][2]["json"]["size"], "1K")
        self.assertEqual(calls[0][2]["json"]["ratio"], "9:16")
        self.assertEqual(
            calls[0][2]["json"]["extra_body"], {"response_format": "url"}
        )

    async def test_four_three_image_and_video_dimensions_are_preserved(self):
        calls = []
        responses = [
            FakeResponse({"data": [{"url": "https://output.agnes-ai.cn/four-three.png"}]})
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            await ai_provider.generate_image("四比三分镜", size="1024*768")

        self.assertEqual(calls[0][2]["json"]["ratio"], "4:3")
        self.assertEqual(ai_provider._agnes_video_v20_dimensions("4:3"), (960, 720))

    async def test_image_relay_places_reference_inside_extra_body(self):
        calls = []
        responses = [
            FakeResponse({
                "data": [{
                    "url": "https://platform-outputs.agnes-ai.space/images/i2i/output.png"
                }]
            })
        ]
        reference = "data:image/png;base64,cmVmZXJlbmNl"
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ):
            url = await ai_provider._request_agnes_image(
                "严格保留输入图片",
                size="1K",
                ratio="1:1",
                input_images=[reference],
            )

        self.assertEqual(
            url,
            "https://platform-outputs.agnes-ai.space/images/i2i/output.png",
        )
        body = calls[0][2]["json"]
        self.assertNotIn("image", body)
        self.assertEqual(body["extra_body"]["image"], [reference])
        self.assertEqual(body["extra_body"]["response_format"], "url")

    async def test_vision_uses_public_image_url_and_agnes_model(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"items":[{"index":0,"summary":"户外画面"}]}'))]
        )
        create = AsyncMock(return_value=completion)
        client = AsyncMock()
        client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        selected = self.settings()
        selected.ai_vision_provider = "agnes"
        selected.agnes_vision_model = "agnes-2.5-flash"
        selected.active_vision_model = "agnes-2.5-flash"
        with patch.object(ai_provider, "settings", selected), patch.object(
            ai_provider, "_agnes_client", return_value=client
        ), patch.object(
            ai_provider,
            "_upload_agnes_visual_frame",
            return_value=("https://media.example.com/frame.jpg", "ai-temp/frame.jpg"),
        ), patch(
            "app.utils.storage.delete_file", return_value=True
        ) as delete_file:
            results = await ai_provider.analyze_visual_segments(
                [{"index": 0, "local_path": "/tmp/frame.jpg"}]
            )

        self.assertEqual(results[0]["provider"], "agnes")
        self.assertEqual(results[0]["model"], "agnes-2.5-flash")
        client.__aenter__.assert_awaited_once_with()
        client.__aexit__.assert_awaited_once()
        request = create.await_args.kwargs
        self.assertEqual(request["model"], "agnes-2.5-flash")
        content = request["messages"][1]["content"]
        self.assertEqual(
            content[-1],
            {
                "type": "image_url",
                "image_url": {"url": "https://media.example.com/frame.jpg"},
            },
        )
        delete_file.assert_called_once_with("ai-temp/frame.jpg")

    async def test_text_video_polls_until_completed_and_clamps_duration(self):
        calls = []
        responses = [
            FakeResponse({"id": "agnes-video-1", "status": "queued"}),
            FakeResponse({"id": "agnes-video-1", "status": "in_progress"}),
            FakeResponse({
                "id": "agnes-video-1",
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/video.mp4"},
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            url = await ai_provider.generate_video(
                "镜头运动", duration=2, aspect_ratio="9:16"
            )

        self.assertEqual(url, "https://output.agnes-ai.cn/video.mp4")
        self.assertEqual(calls[0][1], "https://api.agnes-ai.cn/v1/videos")
        body = calls[0][2]["json"]
        self.assertEqual(body["model"], "agnes-video-v2.0")
        self.assertEqual(body["num_frames"] % 8, 1)
        self.assertEqual(body["frame_rate"], 24)
        self.assertEqual((body["width"], body["height"]), (720, 1280))
        self.assertNotIn("seconds", body)
        self.assertEqual(calls[1][1], "https://api.agnes-ai.cn/agnesapi")
        self.assertEqual(calls[1][2]["params"], {"video_id": "agnes-video-1"})

    async def test_image_video_uses_public_first_frame_and_keyframe_mode(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "agnes-video-2"}),
            FakeResponse({
                "status": "completed",
                "metadata": {
                    "url": "https://output.agnes-ai.cn/image-video.mp4"
                },
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(
            ai_provider,
            "_prepare_agnes_video_first_frame",
            new_callable=AsyncMock,
            return_value="https://media.example.com/frame.png",
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            url = await ai_provider.generate_video(
                "缓慢推进",
                image_url="frames/frame.png",
                duration=15,
            )

        self.assertEqual(url, "https://output.agnes-ai.cn/image-video.mp4")
        body = calls[0][2]["json"]
        self.assertEqual(body["image"], "https://media.example.com/frame.png")
        self.assertNotIn("first_frame", body)
        self.assertEqual(body["num_frames"], 361)

    async def test_public_first_frame_skips_image_relay(self):
        source = "https://media.example.com/frame.png"
        with patch(
            "app.utils.network_security.validate_public_https_url"
        ), patch.object(
            ai_provider, "_request_agnes_image", new_callable=AsyncMock
        ) as relay:
            result = await ai_provider._prepare_agnes_video_first_frame(
                source,
                "16:9",
            )

        self.assertEqual(result, source)
        relay.assert_not_awaited()

    async def test_private_minio_frame_uses_image_to_image_relay(self):
        png = b"\x89PNG\r\n\x1a\nprivate-frame"
        hosted = "https://platform-outputs.agnes-ai.space/images/i2i/output.png"
        with patch.object(
            ai_provider,
            "_read_minio_image",
            return_value=(png, "image/png", ".png"),
        ) as read_minio, patch.object(
            ai_provider,
            "_request_agnes_image",
            new_callable=AsyncMock,
            return_value=hosted,
        ) as relay, patch.object(
            ai_provider,
            "_agnes_public_image_url",
            return_value=hosted,
        ):
            result = await ai_provider._prepare_agnes_video_first_frame(
                "generated/project/frame.png",
                "9:16",
            )

        self.assertEqual(result, hosted)
        read_minio.assert_called_once_with("generated/project/frame.png")
        request = relay.await_args.kwargs
        self.assertEqual(request["size"], "1K")
        self.assertEqual(request["ratio"], "9:16")
        self.assertEqual(len(request["input_images"]), 1)
        self.assertTrue(request["input_images"][0].startswith("data:image/png;base64,"))

    async def test_data_uri_frame_uses_image_to_image_relay(self):
        data_uri = "data:image/png;base64," + base64.b64encode(
            b"\x89PNG\r\n\x1a\ncanvas-frame"
        ).decode()
        hosted = "https://platform-outputs.agnes-ai.space/images/i2i/output.png"
        with patch.object(
            ai_provider,
            "_request_agnes_image",
            new_callable=AsyncMock,
            return_value=hosted,
        ) as relay, patch.object(
            ai_provider,
            "_agnes_public_image_url",
            return_value=hosted,
        ):
            result = await ai_provider._prepare_agnes_video_first_frame(
                data_uri,
                "1:1",
            )

        self.assertEqual(result, hosted)
        self.assertEqual(relay.await_args.kwargs["input_images"], [data_uri])

    async def test_private_frame_relay_flows_into_video_first_frame(self):
        calls = []
        hosted_frame = (
            "https://platform-outputs.agnes-ai.space/images/i2i/relay.png"
        )
        responses = [
            FakeResponse({"data": [{"url": hosted_frame}]}),
            FakeResponse({"id": "agnes-video-relay"}),
            FakeResponse({
                "status": "completed",
                "metadata": {
                    "url": "https://output.agnes-ai.cn/relay-video.mp4"
                },
            }),
        ]
        data_uri = "data:image/png;base64," + base64.b64encode(
            b"\x89PNG\r\n\x1a\nprivate-frame"
        ).decode()
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(
            ai_provider,
            "_agnes_image_input",
            return_value=(data_uri, True),
        ), patch.object(
            ai_provider,
            "_agnes_public_image_url",
            return_value=hosted_frame,
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            video_url = await ai_provider.generate_video(
                "缓慢推进",
                image_url="private/project/frame.png",
                aspect_ratio="16:9",
            )

        self.assertEqual(video_url, "https://output.agnes-ai.cn/relay-video.mp4")
        self.assertTrue(calls[0][1].endswith("/images/generations"))
        relay_body = calls[0][2]["json"]
        self.assertEqual(relay_body["extra_body"]["image"], [data_uri])
        self.assertTrue(calls[1][1].endswith("/videos"))
        self.assertEqual(calls[1][2]["json"]["image"], hosted_frame)

    async def test_video_submit_retries_503_then_succeeds(self):
        calls = []
        responses = [
            FakeResponse(
                {"message": "service busy"},
                status_code=503,
            ),
            FakeResponse({"video_id": "agnes-video-retry"}),
            FakeResponse({
                "status": "completed",
                "metadata": {
                    "url": "https://output.agnes-ai.cn/retried.mp4"
                },
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            url = await ai_provider.generate_video("轻微镜头推进", duration=3)

        self.assertEqual(url, "https://output.agnes-ai.cn/retried.mp4")
        self.assertEqual([call[0] for call in calls[:2]], ["POST", "POST"])
        self.assertEqual(self.submit_limiter.await_count, 2)
        sleep.assert_any_await(0.2)

    async def test_video_poll_retries_429_using_retry_after(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "agnes-video-limited"}),
            FakeResponse(
                {"message": "too many requests"},
                status_code=429,
                headers={"Retry-After": "3"},
            ),
            FakeResponse({
                "status": "completed",
                "metadata": {
                    "url": "https://output.agnes-ai.cn/limited.mp4"
                },
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            url = await ai_provider.generate_video("固定镜头", duration=3)

        self.assertEqual(url, "https://output.agnes-ai.cn/limited.mp4")
        self.assertEqual([call[0] for call in calls], ["POST", "GET", "GET"])
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [0.2, 3.0],
        )

    async def test_video_poll_retries_503_then_recovers(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "agnes-video-busy"}),
            FakeResponse({"message": "service busy"}, status_code=503),
            FakeResponse({
                "status": "completed",
                "metadata": {"url": "https://output.agnes-ai.cn/busy.mp4"},
            }),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            url = await ai_provider.generate_video("固定镜头", duration=3)

        self.assertEqual(url, "https://output.agnes-ai.cn/busy.mp4")
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [0.2, 0.4],
        )

    async def test_video_poll_non_retryable_error_is_chinese(self):
        calls = []
        responses = [
            FakeResponse({"video_id": "agnes-video-invalid"}),
            FakeResponse({"message": "invalid video id"}, status_code=400),
        ]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(
                responses, calls, *args, **kwargs
            ),
        ), patch.object(ai_provider.asyncio, "sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(
                RuntimeError,
                "Agnes AI 文生视频任务查询失败（HTTP 400）：invalid video id",
            ):
                await ai_provider.generate_video("固定镜头", duration=3)


if __name__ == "__main__":
    unittest.main()
