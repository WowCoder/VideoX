"""时长解析工具（从 MVP2 迁移）。"""


def parse_duration(value, fallback: int = 8) -> int:
    """解析时长字符串或数字，返回秒数。

    支持：
    - "MM:SS" 格式 → 分钟*60+秒
    - 纯数字 → 秒
    - 其他 → fallback

    结果 clamp 到 2-300 秒。
    """
    if value is None:
        return fallback

    if isinstance(value, (int, float)):
        seconds = int(value)
    else:
        text = str(value).strip()
        if not text:
            return fallback

        # MM:SS 格式
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                try:
                    minutes = int(parts[0])
                    secs = int(parts[1])
                    seconds = minutes * 60 + secs
                except ValueError:
                    return fallback
            else:
                return fallback
        else:
            try:
                seconds = int(text)
            except ValueError:
                return fallback

    return max(2, min(300, seconds))


def format_duration(seconds: int) -> str:
    """秒数格式化为 MM:SS。"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def split_long_text(value: str) -> list[str]:
    """长文本拆分（从 MVP2 迁移）。

    - ≤80 字 → 原样返回
    - >80 字 → 按句号/感叹号/问号/分号切句，>72 字分块
    """
    if not value or len(value) <= 80:
        return [value] if value else []

    import re
    # 按句末标点切句
    sentences = re.split(r'(?<=[。！？；!?;])', value)
    sentences = [s.strip() for s in sentences if s.strip()]

    result = []
    chunk = ""
    for sentence in sentences:
        if len(chunk) + len(sentence) > 72 and chunk:
            result.append(chunk)
            chunk = sentence
        else:
            chunk += sentence
    if chunk:
        result.append(chunk)

    return result
