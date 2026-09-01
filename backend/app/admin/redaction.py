"""Admin API 服务端脱敏工具。"""

import re
from typing import Any


SENSITIVE_KEYS = {
    "api_key", "authorization", "password", "password_hash", "private_key",
    "refresh_token", "secret", "signature", "sign", "sms_code", "token",
}


def mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "***"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_KEYS or any(part in normalized for part in SENSITIVE_KEYS):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = redact_mapping(item)
        return result
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"([?&](?:X-Amz-[^=]+|Signature|token)=[^&]+)", "[REDACTED]", value, flags=re.I)
    return value
