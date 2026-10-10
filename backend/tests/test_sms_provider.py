import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import sms_provider


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str | int] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def setex(self, key, seconds, value):
        self.values[key] = value
        self.expirations[key] = seconds
        return True

    async def get(self, key):
        value = self.values.get(key)
        return None if value is None else str(value)

    async def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    async def decr(self, key):
        value = int(self.values.get(key, 0)) - 1
        self.values[key] = value
        return value

    async def expire(self, key, seconds):
        self.expirations[key] = seconds
        return True

    async def ttl(self, key):
        return self.expirations.get(key, -1)

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
            self.expirations.pop(key, None)
        return deleted

    async def eval(self, _script, _number_of_keys, code_key, attempt_key, expected):
        if self.values.get(code_key) == expected:
            await self.delete(code_key, attempt_key)
            return 1
        return 0

    async def aclose(self):
        self.closed = True


def sms_settings(**overrides):
    values = {
        "has_sms": True,
        "redis_url": "redis://test/0",
        "sms_access_key_id": "test-key-id",
        "sms_access_key_secret": "test-key-secret",
        "sms_sign_name": "Example App",
        "sms_template_code": "SMS_EXAMPLE",
        "sms_code_ttl_seconds": 300,
        "sms_resend_interval_seconds": 60,
        "sms_hourly_limit": 5,
        "sms_daily_limit": 10,
        "sms_max_verify_attempts": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SmsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_send_stores_code_and_rate_limit_reservation(self):
        redis = FakeRedis()
        with (
            patch.object(sms_provider, "settings", sms_settings()),
            patch("redis.asyncio.from_url", return_value=redis),
            patch.object(sms_provider, "generate_code", return_value="123456"),
            patch.object(
                sms_provider,
                "_send_code_via_aliyun",
                new=AsyncMock(return_value=True),
            ) as provider,
        ):
            sent = await sms_provider.send_code("18888888888")

        self.assertTrue(sent)
        self.assertEqual(redis.values["openvma:sms-code:18888888888"], "123456")
        self.assertIn("openvma:sms-cooldown:18888888888", redis.values)
        provider.assert_awaited_once_with("18888888888", "123456")
        self.assertTrue(redis.closed)

    async def test_resend_during_cooldown_returns_rate_limit_error(self):
        redis = FakeRedis()
        with (
            patch.object(sms_provider, "settings", sms_settings()),
            patch("redis.asyncio.from_url", return_value=redis),
            patch.object(sms_provider, "generate_code", return_value="123456"),
            patch.object(
                sms_provider,
                "_send_code_via_aliyun",
                new=AsyncMock(return_value=True),
            ),
        ):
            self.assertTrue(await sms_provider.send_code("18888888888"))
            with self.assertRaises(sms_provider.SmsRateLimitError) as context:
                await sms_provider.send_code("18888888888")

        self.assertEqual(context.exception.retry_after_seconds, 60)

    async def test_provider_failure_releases_phone_quota(self):
        redis = FakeRedis()
        with (
            patch.object(sms_provider, "settings", sms_settings()),
            patch("redis.asyncio.from_url", return_value=redis),
            patch.object(
                sms_provider,
                "_send_code_via_aliyun",
                new=AsyncMock(return_value=False),
            ),
        ):
            sent = await sms_provider.send_code("18888888888")

        self.assertFalse(sent)
        self.assertNotIn("openvma:sms-cooldown:18888888888", redis.values)
        self.assertFalse(any("sms-hourly" in key for key in redis.values))
        self.assertFalse(any("sms-daily" in key for key in redis.values))

    async def test_hourly_limit_is_enforced_after_cooldowns_expire(self):
        redis = FakeRedis()
        phone = "18888888888"
        with patch.object(
            sms_provider,
            "settings",
            sms_settings(sms_hourly_limit=2, sms_daily_limit=10),
        ):
            await sms_provider._reserve_send_slot(redis, phone)
            await redis.delete(f"{sms_provider.COOLDOWN_KEY_PREFIX}{phone}")
            await sms_provider._reserve_send_slot(redis, phone)
            await redis.delete(f"{sms_provider.COOLDOWN_KEY_PREFIX}{phone}")
            with self.assertRaisesRegex(
                sms_provider.SmsRateLimitError,
                "本小时",
            ):
                await sms_provider._reserve_send_slot(redis, phone)

    async def test_correct_code_can_only_be_consumed_once(self):
        redis = FakeRedis()
        redis.values["openvma:sms-code:18888888888"] = "123456"
        with (
            patch.object(sms_provider, "settings", sms_settings()),
            patch("redis.asyncio.from_url", return_value=redis),
        ):
            self.assertTrue(await sms_provider.verify_code("18888888888", "123456"))
            self.assertFalse(await sms_provider.verify_code("18888888888", "123456"))

    async def test_code_is_invalidated_after_too_many_wrong_attempts(self):
        redis = FakeRedis()
        redis.values["openvma:sms-code:18888888888"] = "123456"
        with (
            patch.object(sms_provider, "settings", sms_settings()),
            patch("redis.asyncio.from_url", return_value=redis),
        ):
            for _ in range(5):
                self.assertFalse(await sms_provider.verify_code("18888888888", "000000"))

        self.assertNotIn("openvma:sms-code:18888888888", redis.values)
        self.assertNotIn("openvma:sms-attempts:18888888888", redis.values)


if __name__ == "__main__":
    unittest.main()
