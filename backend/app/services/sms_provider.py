"""阿里云短信服务 — 验证码发送与 Redis 一次性校验。

未配置凭证时明确返回不可用，不生成或接受开发验证码。
配置凭证后：调用阿里云 SendSms API 发送真实短信。

配置项（.env）：
    SMS_ACCESS_KEY_ID        阿里云 AccessKey ID
    SMS_ACCESS_KEY_SECRET    阿里云 AccessKey Secret
    SMS_SIGN_NAME            短信签名名称
    SMS_TEMPLATE_CODE        短信模板 CODE
"""

import hmac
import logging
import secrets

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 300
CODE_KEY_PREFIX = "openvma:sms-code:"


def generate_code() -> str:
    """生成不可预测的 6 位验证码。"""
    return f"{secrets.randbelow(900000) + 100000}"


async def _store_code(phone: str, code: str) -> None:
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.setex(f"{CODE_KEY_PREFIX}{phone}", CODE_TTL_SECONDS, code)
    finally:
        await redis.close()


async def send_code(phone: str) -> bool:
    """发送验证码。返回是否成功。

    已配置凭证时调用阿里云短信 API 发送真实短信。
    """
    if not settings.has_sms:
        logger.error("短信服务未配置，拒绝生成验证码")
        return False

    code = generate_code()

    # 生产模式：调用阿里云短信 API
    try:
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
        from alibabacloud_tea_openapi.models import Config

        config = Config(
            access_key_id=settings.sms_access_key_id,
            access_key_secret=settings.sms_access_key_secret,
            endpoint="dysmsapi.aliyuncs.com",
        )
        client = Client(config)

        send_req = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=settings.sms_sign_name,
            template_code=settings.sms_template_code,
            template_param=f'{{"code":"{code}"}}',
        )
        resp = client.send_sms(send_req)
        if resp.body.code == "OK":
            await _store_code(phone, code)
            logger.info("验证码已发送到 %s", phone)
            return True
        else:
            logger.error("阿里云短信发送失败：%s %s", resp.body.code, resp.body.message)
            return False
    except ImportError:
        # SDK 未安装，降级为 httpx 直接调用 REST API
        logger.warning("alibabacloud-dysmsapi SDK 未安装，尝试使用 httpx 直接调用")
        sent = await _send_code_via_httpx(phone, code)
        if sent:
            await _store_code(phone, code)
        return sent
    except Exception as e:
        logger.error("发送短信失败：%s", e)
        return False


async def _send_code_via_httpx(phone: str, code: str) -> bool:
    """使用 httpx 直接调用阿里云短信 REST API（SDK 未安装时的降级方案）。

    阿里云短信需要 HMAC-SHA1 签名，这里使用 aliyun-python-sdk-core 的签名逻辑。
    如果 SDK 均未安装，则记录日志并返回 False。
    """
    try:
        import httpx
        import hmac
        import hashlib
        import base64
        import urllib.parse
        import time
        from datetime import datetime, timezone

        # 构建公共参数
        params = {
            "PhoneNumbers": phone,
            "SignName": settings.sms_sign_name,
            "TemplateCode": settings.sms_template_code,
            "TemplateParam": f'{{"code":"{code}"}}',
            "AccessKeyId": settings.sms_access_key_id,
            "Format": "JSON",
            "Version": "2017-05-25",
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "SignatureVersion": "1.0",
            "SignatureNonce": str(int(time.time() * 1000)),
            "Action": "SendSms",
            "RegionId": "cn-hangzhou",
        }

        # 计算签名
        sorted_params = sorted(params.items())
        canonicalized = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted_params
        )
        string_to_sign = f"GET&%2F&{urllib.parse.quote(canonicalized, safe='')}"
        hmac_obj = hmac.new(
            (settings.sms_access_key_secret + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")
        params["Signature"] = signature

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://dysmsapi.aliyuncs.com/", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("Code") == "OK":
                logger.info("验证码已发送到 %s（httpx）", phone)
                return True
            else:
                logger.error(
                    "阿里云短信发送失败：%s %s",
                    data.get("Code"),
                    data.get("Message"),
                )
                return False
    except Exception as e:
        logger.error("httpx 调用短信 API 失败：%s", e)
        return False


async def verify_code(phone: str, code: str) -> bool:
    """验证验证码。

    验证成功后自动删除验证码（一次性使用）。
    """
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    key = f"{CODE_KEY_PREFIX}{phone}"
    try:
        stored = await redis.get(key)
        if not stored or not hmac.compare_digest(stored, code):
            return False
        await redis.delete(key)
        return True
    finally:
        await redis.close()
