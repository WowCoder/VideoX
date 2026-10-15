"""阿里云短信服务：发送手机验证码并通过 Redis 完成限流和一次性校验。

短信模板参数固定为 ``code``，即向阿里云传递
``{"code":"123456"}``。未完整配置凭证时不会生成或接受开发验证码。
"""

import asyncio
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

CODE_KEY_PREFIX = "videox:sms-code:"
ATTEMPT_KEY_PREFIX = "videox:sms-attempts:"
COOLDOWN_KEY_PREFIX = "videox:sms-cooldown:"
HOURLY_KEY_PREFIX = "videox:sms-hourly:"
DAILY_KEY_PREFIX = "videox:sms-daily:"
CHINA_TIMEZONE = timezone(timedelta(hours=8))


class SmsRateLimitError(RuntimeError):
    """手机号维度的短信限流。"""

    def __init__(self, message: str, retry_after_seconds: int):
        super().__init__(message)
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(frozen=True)
class _SendReservation:
    cooldown_key: str
    counter_keys: tuple[str, ...]


def generate_code() -> str:
    """生成不可预测的 6 位数字验证码。"""
    return f"{secrets.randbelow(900000) + 100000}"


def _masked_phone(phone: str) -> str:
    """日志中只保留手机号前三位和后四位。"""
    if len(phone) < 7:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


async def _rollback_send_reservation(redis, reservation: _SendReservation) -> None:
    await redis.delete(reservation.cooldown_key)
    for key in reservation.counter_keys:
        remaining = await redis.decr(key)
        if remaining <= 0:
            await redis.delete(key)


async def _reserve_send_slot(redis, phone: str) -> _SendReservation:
    """预留一次发送额度，防止同一手机号并发绕过限流。"""
    now = datetime.now(CHINA_TIMEZONE)
    cooldown_key = f"{COOLDOWN_KEY_PREFIX}{phone}"
    cooldown_created = await redis.set(
        cooldown_key,
        "1",
        ex=settings.sms_resend_interval_seconds,
        nx=True,
    )
    if not cooldown_created:
        retry_after = await redis.ttl(cooldown_key)
        raise SmsRateLimitError("验证码发送过于频繁，请稍后重试", retry_after)

    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    limits = (
        (
            f"{HOURLY_KEY_PREFIX}{now:%Y%m%d%H}:{phone}",
            settings.sms_hourly_limit,
            int((next_hour - now).total_seconds()) + 60,
            "该手机号本小时验证码发送次数已达上限",
        ),
        (
            f"{DAILY_KEY_PREFIX}{now:%Y%m%d}:{phone}",
            settings.sms_daily_limit,
            int((next_day - now).total_seconds()) + 60,
            "该手机号今日验证码发送次数已达上限",
        ),
    )
    reserved_keys: list[str] = []
    try:
        for key, limit, expiry, message in limits:
            count = await redis.incr(key)
            reserved_keys.append(key)
            if count == 1:
                await redis.expire(key, expiry)
            if count > limit:
                retry_after = await redis.ttl(key)
                reservation = _SendReservation(cooldown_key, tuple(reserved_keys))
                await _rollback_send_reservation(redis, reservation)
                raise SmsRateLimitError(message, retry_after)
    except SmsRateLimitError:
        raise
    except Exception:
        reservation = _SendReservation(cooldown_key, tuple(reserved_keys))
        await _rollback_send_reservation(redis, reservation)
        raise

    return _SendReservation(cooldown_key, tuple(reserved_keys))


async def _send_code_via_aliyun(phone: str, code: str) -> bool:
    """优先使用阿里云官方 SDK；缺少 SDK 时使用签名后的 HTTP API。"""
    try:
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
        from alibabacloud_tea_openapi.models import Config
    except ImportError:
        logger.warning("阿里云短信 SDK 未安装，尝试使用 HTTP API")
        return await _send_code_via_httpx(phone, code)

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

    # 官方 SDK 是同步请求，放到线程中执行，避免阻塞 FastAPI 事件循环。
    response = await asyncio.to_thread(client.send_sms, send_req)
    body = response.body
    provider_code = getattr(body, "code", "")
    request_id = getattr(body, "request_id", "")
    if provider_code == "OK":
        logger.info(
            "阿里云短信发送成功 phone=%s request_id=%s",
            _masked_phone(phone),
            request_id,
        )
        return True

    logger.error(
        "阿里云短信发送失败 phone=%s code=%s message=%s request_id=%s",
        _masked_phone(phone),
        provider_code,
        getattr(body, "message", ""),
        request_id,
    )
    return False


async def send_code(phone: str) -> bool:
    """发送真实验证码，并仅在供应商确认成功后写入 Redis。"""
    if not settings.has_sms:
        logger.error("短信服务未完整配置，拒绝生成验证码")
        return False

    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    reservation: _SendReservation | None = None
    provider_sent = False
    try:
        reservation = await _reserve_send_slot(redis, phone)
        code = generate_code()
        provider_sent = await _send_code_via_aliyun(phone, code)
        if not provider_sent:
            await _rollback_send_reservation(redis, reservation)
            return False

        await redis.setex(
            f"{CODE_KEY_PREFIX}{phone}",
            settings.sms_code_ttl_seconds,
            code,
        )
        await redis.delete(f"{ATTEMPT_KEY_PREFIX}{phone}")
        return True
    except SmsRateLimitError:
        raise
    except Exception as error:
        # 供应商未成功发送时释放额度；已发送但 Redis 写入失败时
        # 保留冷却和频率计数，避免连续向用户发送多条短信。
        if reservation is not None and not provider_sent:
            try:
                await _rollback_send_reservation(redis, reservation)
            except Exception:
                logger.exception("短信发送预留额度回滚失败")
        logger.error("发送短信失败 phone=%s error=%s", _masked_phone(phone), error)
        return False
    finally:
        await redis.aclose()


async def _send_code_via_httpx(phone: str, code: str) -> bool:
    """使用阿里云 RPC 签名调用 SendSms API，作为 SDK 缺失时的降级方案。"""
    try:
        import base64
        import hashlib
        import httpx
        import urllib.parse

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
            "SignatureNonce": secrets.token_hex(16),
            "Action": "SendSms",
            "RegionId": "cn-hangzhou",
        }
        sorted_params = sorted(params.items())
        canonicalized = "&".join(
            f"{urllib.parse.quote(key, safe='')}={urllib.parse.quote(value, safe='')}"
            for key, value in sorted_params
        )
        string_to_sign = f"GET&%2F&{urllib.parse.quote(canonicalized, safe='')}"
        hmac_object = hmac.new(
            (settings.sms_access_key_secret + "&").encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        )
        params["Signature"] = base64.b64encode(hmac_object.digest()).decode()

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://dysmsapi.aliyuncs.com/", params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("Code") == "OK":
            logger.info(
                "阿里云短信发送成功 phone=%s request_id=%s transport=http",
                _masked_phone(phone),
                data.get("RequestId", ""),
            )
            return True
        logger.error(
            "阿里云短信发送失败 phone=%s code=%s message=%s request_id=%s transport=http",
            _masked_phone(phone),
            data.get("Code", ""),
            data.get("Message", ""),
            data.get("RequestId", ""),
        )
        return False
    except Exception as error:
        logger.error(
            "HTTP API 调用阿里云短信失败 phone=%s error=%s",
            _masked_phone(phone),
            error,
        )
        return False


async def verify_code(phone: str, code: str) -> bool:
    """校验并原子消费验证码；连续输错达上限后立即作废。"""
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    code_key = f"{CODE_KEY_PREFIX}{phone}"
    attempt_key = f"{ATTEMPT_KEY_PREFIX}{phone}"
    try:
        stored = await redis.get(code_key)
        if not stored:
            return False

        if hmac.compare_digest(stored, code):
            # 只有仍与本次读取值一致时才删除，保证并发校验仅一次成功。
            consumed = await redis.eval(
                """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    redis.call('DEL', KEYS[1], KEYS[2])
                    return 1
                end
                return 0
                """,
                2,
                code_key,
                attempt_key,
                stored,
            )
            return bool(consumed)

        attempts = await redis.incr(attempt_key)
        if attempts == 1:
            await redis.expire(attempt_key, settings.sms_code_ttl_seconds)
        if attempts >= settings.sms_max_verify_attempts:
            await redis.delete(code_key, attempt_key)
        return False
    finally:
        await redis.aclose()
