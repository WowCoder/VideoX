import unittest
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.services import ai_provider


class FakeResponse:
    def __init__(self, payload, status_error: Exception | None = None):
        self.payload = payload
        self.status_error = status_error

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
        responses = [FakeResponse({"output": {"task_id": "video-task"}})]
        with patch.object(ai_provider, "settings", self.settings()), patch.object(
            ai_provider.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: RecordingAsyncClient(responses, calls, *args, **kwargs),
        ):
            task_id = await ai_provider.generate_video("镜头运动", image_url="https://example.com/frame.png")

        self.assertEqual(task_id, "video-task")
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


if __name__ == "__main__":
    unittest.main()
