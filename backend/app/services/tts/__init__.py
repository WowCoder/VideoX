"""供应商无关的 AI 配音服务。"""

from app.services.tts.dashscope import DashScopeTTSProvider
from app.services.tts.models import TTSRequest, TTSResult

__all__ = ["DashScopeTTSProvider", "TTSRequest", "TTSResult"]
