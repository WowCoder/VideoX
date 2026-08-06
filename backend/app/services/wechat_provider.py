"""微信开放平台 OAuth 服务。

未配置凭证时返回 RuntimeError。
配置后：生成扫码登录 URL、用 code 换 access_token、获取用户信息。

配置项（.env）：
    WECHAT_APP_ID         微信开放平台 AppID
    WECHAT_APP_SECRET     微信开放平台 AppSecret
    WECHAT_REDIRECT_URI   回调地址（前端页面 URL）
"""

import httpx

from app.config import get_settings

settings = get_settings()


def get_qrcode_url(state: str = "") -> str:
    """生成微信扫码登录二维码 URL。

    返回前端可直接跳转的微信开放平台扫码授权地址。
    """
    if not settings.has_wechat:
        raise RuntimeError("微信开放平台凭证未配置")
    return (
        f"https://open.weixin.qq.com/connect/qrconnect"
        f"?appid={settings.wechat_app_id}"
        f"&redirect_uri={settings.wechat_redirect_uri}"
        f"&response_type=code"
        f"&scope=snsapi_login"
        f"&state={state or 'openvma'}"
        f"#wechat_redirect"
    )


async def exchange_code_for_token(code: str) -> dict:
    """用授权 code 换取 access_token。

    返回微信 API 响应 JSON，包含 access_token、openid、unionid 等字段。
    失败时抛出 httpx.HTTPStatusError。
    """
    if not settings.has_wechat:
        raise RuntimeError("微信开放平台凭证未配置")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": settings.wechat_app_id,
                "secret": settings.wechat_app_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_info(access_token: str, openid: str) -> dict:
    """获取微信用户信息。

    返回微信 API 响应 JSON，包含 nickname、headimgurl、openid、unionid 等字段。
    失败时抛出 httpx.HTTPStatusError。
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={"access_token": access_token, "openid": openid},
        )
        resp.raise_for_status()
        return resp.json()
