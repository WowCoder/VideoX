"""TTS Provider 的标准请求与结果。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class TTSRequest:
    text: str
    model: str
    voice: str
    language: str = "Chinese"
    instruction: str = ""
    emotion: str = ""
    request_hash: str = ""


@dataclass(slots=True)
class TTSResult:
    audio_bytes: bytes
    content_type: str
    provider_request_id: str | None = None
    input_characters: int = 0
    billed_characters: int = 0
    raw_metadata: dict = field(default_factory=dict)
