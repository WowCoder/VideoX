"""TTS 文本规范化、计费估算和幂等哈希。"""

import hashlib
import json
import re
import unicodedata


_SPACE_RE = re.compile(r"[ \t\f\v]+")
_NEWLINE_RE = re.compile(r"\s*\n\s*")

SUPPORTED_TTS_MODELS = {
    "qwen-audio-3.0-tts-flash",
    "qwen3-tts-instruct-flash",
    "qwen3-tts-flash",
}


def normalize_tts_text(text: str) -> str:
    # NFC 合并等价码位但保留中文全角标点；标点形态会影响 TTS 停顿和情绪。
    text = unicodedata.normalize("NFC", text or "")
    text = _NEWLINE_RE.sub("\n", text.strip())
    return _SPACE_RE.sub(" ", text)


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_tts_text(text).encode("utf-8")).hexdigest()


def dashscope_billable_characters(text: str) -> int:
    """按千问公开计费约定估算：中日韩统一表意文字计 2，其余字符计 1。"""
    total = 0
    for char in normalize_tts_text(text):
        codepoint = ord(char)
        is_cjk = (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x2FA1F
        )
        total += 2 if is_cjk else 1
    return total


def make_request_hash(*, provider: str, model: str, voice: str, text: str, language: str, instruction: str, emotion: str, target_duration_ms: int = 0) -> str:
    payload = {
        "adapter_version": 1,
        "provider": provider,
        "model": model,
        "voice": voice,
        "text": normalize_tts_text(text),
        "language": language,
        "instruction": normalize_tts_text(instruction),
        "emotion": emotion.strip().lower(),
        # Provider 原始请求的可复用边界；48kHz/stereo 是后处理产物，
        # 不应让项目内不同目标时长复用已经拉伸过的编辑文件。
        "format": "provider-original-v1",
        "target_duration_ms": max(0, target_duration_ms),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def validate_tts_selection(model: str, voice: str) -> None:
    """拒绝最常见的跨模型音色误配；完整列表仍以供应商返回为准。"""
    if model not in SUPPORTED_TTS_MODELS:
        raise ValueError("当前仅支持已配置的千问 AI 配音模型")
    qwen_audio_voices = {
        "longanfengyue", "longanyuanfei", "longanlingxi", "longanxiaoxin",
        "longanhuan_v3.6", "longjielidou_v3.6", "longpaopao_v3.6",
        "longhuohuo_v3.6", "longchuanshu_v3.6", "loongmary", "loongeva_v3.6", "loongjohn",
    }
    if model.startswith("qwen-audio-") and not (
        voice in qwen_audio_voices or voice.startswith(f"{model}-")
    ):
        raise ValueError("所选音色不兼容 Qwen-Audio-TTS 模型")
    if model.startswith("qwen3-tts-") and voice.startswith(("longan", "longjie", "longpao", "longhuo", "longchuan")):
        raise ValueError("所选音色不兼容 Qwen3-TTS 模型")
