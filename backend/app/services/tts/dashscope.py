"""千问/DashScope TTS Provider。"""

import asyncio
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import get_settings
from app.services.tts.models import TTSRequest, TTSResult
from app.services.tts.normalization import dashscope_billable_characters
from app.utils.network_security import validate_external_media_url


class DashScopeTTSProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.has_tts:
            raise RuntimeError("AI 配音未启用，请配置 AI_TTS_PROVIDER=dashscope、DASHSCOPE_API_KEY 和音色")

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if request.model.startswith("qwen-audio-"):
            return await self._synthesize_qwen_audio(request)
        return await self._synthesize_qwen3(request)

    async def _synthesize_qwen_audio(self, request: TTSRequest) -> TTSResult:
        """使用官方非实时 HTTP API，避免 Worker 维护长连接和额外 SDK 状态。"""
        rendered_text = request.text
        if request.emotion and not rendered_text.lstrip().startswith("["):
            rendered_text = f"[{request.emotion}]{rendered_text}"
        input_payload: dict[str, Any] = {
            "text": rendered_text,
            "voice": request.voice,
            "format": "wav",
            "sample_rate": self.settings.ai_tts_output_sample_rate,
            "language_hints": ["zh" if request.language.lower().startswith(("chinese", "zh")) else "en"],
            "enable_aigc_tag": True,
        }
        if request.instruction:
            input_payload["instruction"] = request.instruction
        endpoint = f"{self.settings.dashscope_api_url.rstrip('/')}/services/audio/tts/SpeechSynthesizer"
        body = await self._post_json(endpoint, {"model": request.model, "input": input_payload})
        output = body.get("output") if isinstance(body, dict) else None
        audio = output.get("audio") if isinstance(output, dict) else None
        audio_url = audio.get("url") if isinstance(audio, dict) else None
        if not isinstance(audio_url, str) or not audio_url:
            raise RuntimeError("千问语音响应缺少音频 URL")
        audio_bytes, content_type = await self._download_audio(audio_url)
        usage = body.get("usage") if isinstance(body, dict) else {}
        billed = int((usage or {}).get("characters") or dashscope_billable_characters(rendered_text))
        return TTSResult(
            audio_bytes=audio_bytes,
            content_type=content_type,
            provider_request_id=str(body.get("request_id") or "") or None,
            input_characters=len(rendered_text),
            billed_characters=billed,
            raw_metadata={"expires_at": audio.get("expires_at") if isinstance(audio, dict) else None},
        )

    async def _synthesize_qwen3(self, request: TTSRequest) -> TTSResult:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": {
                "text": request.text,
                "voice": request.voice,
                "language_type": request.language,
            },
        }
        if request.instruction and request.model.startswith("qwen3-tts-instruct-"):
            payload["input"]["instructions"] = request.instruction
            payload["input"]["optimize_instructions"] = True
        endpoint = f"{self.settings.dashscope_api_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
        body = await self._post_json(endpoint, payload)
        output = body.get("output") if isinstance(body, dict) else None
        audio = output.get("audio") if isinstance(output, dict) else None
        audio_url = audio.get("url") if isinstance(audio, dict) else None
        if not audio_url and isinstance(output, dict):
            audio_url = output.get("url")
        if not isinstance(audio_url, str) or not audio_url:
            raise RuntimeError("千问语音响应缺少音频 URL")
        audio_bytes, content_type = await self._download_audio(audio_url)
        usage = body.get("usage") if isinstance(body, dict) else {}
        billed = int((usage or {}).get("characters") or dashscope_billable_characters(request.text))
        return TTSResult(
            audio_bytes=audio_bytes,
            content_type=content_type,
            provider_request_id=str(body.get("request_id") or "") or None,
            input_characters=len(request.text),
            billed_characters=billed,
            raw_metadata={"expires_at": audio.get("expires_at") if isinstance(audio, dict) else None},
        )

    async def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.dashscope_api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(float(self.settings.ai_tts_request_timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response: httpx.Response | None = None
            for attempt in range(3):
                try:
                    response = await client.post(endpoint, headers=headers, json=payload)
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == 2:
                        raise RuntimeError("千问语音服务网络请求连续失败") from None
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                break
            if response is None:
                raise RuntimeError("千问语音服务没有返回响应")
            if response.status_code >= 400:
                try:
                    error = response.json()
                    message = error.get("message") or error.get("code") or "请求失败"
                except ValueError:
                    message = "请求失败"
                raise RuntimeError(f"千问语音服务返回 {response.status_code}：{str(message)[:200]}")
            body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("千问语音服务返回了无效 JSON")
        return body

    async def _download_audio(self, url: str) -> tuple[bytes, str]:
        url = normalize_dashscope_audio_url(url)
        validate_external_media_url(url)
        timeout = httpx.Timeout(float(self.settings.ai_tts_download_timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            current_url = url
            for redirect_count in range(4):
                validate_external_media_url(current_url)
                response = await client.get(current_url)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count == 3:
                        raise RuntimeError("千问音频下载发生了无效或过多的重定向")
                    current_url = normalize_dashscope_audio_url(str(response.url.join(location)))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "audio/mpeg").split(";", 1)[0]
                if not content_type.startswith("audio/") or not response.content:
                    raise RuntimeError("千问服务返回的音频文件无效")
                if len(response.content) > 100 * 1024 * 1024:
                    raise RuntimeError("单条配音文件超过 100MB 限制")
                return response.content, content_type
        raise RuntimeError("无法下载千问语音结果")


def normalize_dashscope_audio_url(url: str) -> str:
    """将千问官方 OSS 结果的 HTTP 临时地址升级为 HTTPS，不放宽全局 SSRF 规则。"""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    is_dashscope_oss = (
        hostname.startswith("dashscope-result-")
        and ".oss-" in hostname
        and hostname.endswith(".aliyuncs.com")
    )
    if (
        parsed.scheme.lower() == "http"
        and is_dashscope_oss
        and not parsed.username
        and not parsed.password
        and parsed.port is None
    ):
        return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return url
