"""将旁白切成可独立重生成的自然语义段。"""

import re

from app.services.tts.normalization import normalize_tts_text


_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;…])")
_SOFT_RE = re.compile(r"(?<=[，,、：:])")


def _visible_length(text: str) -> int:
    return len(re.sub(r"\[[^\]]{1,40}\]", "", text).strip())


def _split_long(text: str, maximum: int) -> list[str]:
    if _visible_length(text) <= maximum:
        return [text]
    pieces = [part.strip() for part in _SOFT_RE.split(text) if part.strip()]
    if len(pieces) == 1:
        return [text[index:index + maximum].strip() for index in range(0, len(text), maximum)]
    result: list[str] = []
    current = ""
    for piece in pieces:
        if current and _visible_length(current + piece) > maximum:
            result.append(current)
            current = piece
        else:
            current += piece
    if current:
        result.append(current)
    return result


def segment_text(text: str, *, minimum: int = 15, maximum: int = 80) -> list[str]:
    normalized = normalize_tts_text(text)
    if not normalized:
        return []
    hard_parts: list[str] = []
    for paragraph in normalized.splitlines():
        hard_parts.extend(part.strip() for part in _SENTENCE_RE.split(paragraph) if part.strip())
    pieces = [piece for part in hard_parts for piece in _split_long(part, maximum)]
    result: list[str] = []
    for piece in pieces:
        if result and _visible_length(piece) < minimum and _visible_length(result[-1] + piece) <= maximum:
            result[-1] += piece
        else:
            result.append(piece)
    return result


def speaking_weight(text: str) -> float:
    visible = _visible_length(text)
    punctuation = len(re.findall(r"[，,、：:；;。！？!?…]", text))
    return max(1.0, visible + punctuation * 2.5)
