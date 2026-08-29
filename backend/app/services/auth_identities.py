"""登录身份的标准化规则。

业务数据始终关联 users.id；邮箱、手机号和微信只作为可替换、可并存的认证身份。
"""

import re


EMAIL_PROVIDER = "email"
PHONE_PROVIDER = "phone"
WECHAT_PROVIDER = "wechat"


def normalize_email_identity(value: str) -> str:
    return value.strip().lower()


def normalize_phone_identity(value: str) -> str:
    """将中国大陆手机号统一为 E.164 形式。"""
    digits = re.sub(r"\D", "", value)
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise ValueError("请输入正确的 11 位手机号")
    return f"+86{digits}"


def phone_from_identity(identifier: str) -> str:
    if not identifier.startswith("+86"):
        raise ValueError("手机号身份格式无效")
    return identifier[3:]


def wechat_identity_identifier(
    unionid: str | None,
    openid: str,
    provider_app_id: str | None = None,
) -> str:
    """优先使用跨应用 unionid；缺失时退回当前开放平台的 openid。"""
    normalized_unionid = (unionid or "").strip()
    if normalized_unionid:
        return f"unionid:{normalized_unionid}"
    normalized_openid = openid.strip()
    if not normalized_openid:
        raise ValueError("微信身份缺少 openid")
    app_scope = (provider_app_id or "legacy").strip() or "legacy"
    return f"openid:{app_scope}:{normalized_openid}"
