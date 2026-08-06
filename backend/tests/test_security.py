import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings
from app.main import _readiness_status
from app.utils.network_security import validate_external_media_url


class ProductionSettingsTests(unittest.TestCase):
    def test_production_rejects_default_jwt_secret(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                environment="production",
                cors_origins="https://app.example.com",
                trusted_hosts="api.example.com",
                rate_limit_enabled=True,
                minio_public_endpoint="media.example.com",
                minio_public_secure=True,
            )

    def test_production_accepts_explicit_security_configuration(self):
        settings = Settings(
            _env_file=None,
            environment="production",
            jwt_secret="x" * 48,
            cors_origins="https://app.example.com",
            trusted_hosts="api.example.com",
            rate_limit_enabled=True,
            minio_public_endpoint="media.example.com",
            minio_public_secure=True,
            local_ai_api_key="local-ai-token-that-is-long-enough",
        )
        self.assertEqual(settings.trusted_host_list, ["api.example.com"])

    def test_production_rejects_unprotected_local_ai(self):
        with self.assertRaisesRegex(ValidationError, "LOCAL_AI_API_KEY"):
            Settings(
                _env_file=None,
                environment="production",
                jwt_secret="x" * 48,
                cors_origins="https://app.example.com",
                trusted_hosts="api.example.com",
                rate_limit_enabled=True,
                minio_public_endpoint="media.example.com",
                minio_public_secure=True,
            )

    def test_rejects_non_1024_embedding_configuration(self):
        with self.assertRaisesRegex(ValidationError, "1024"):
            Settings(_env_file=None, ai_embedding_dimensions=768)

    def test_rejects_invalid_database_pool_configuration(self):
        with self.assertRaisesRegex(ValidationError, "DB_POOL_SIZE"):
            Settings(_env_file=None, db_pool_size=0)

    def test_shared_environment_can_contain_compose_only_values(self):
        settings = Settings(_env_file=None, compose_only_value="ignored")
        self.assertEqual(settings.environment, "development")


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_dependencies_ready(self):
        async def healthy():
            return None

        with (
            patch("app.main._check_database", side_effect=healthy),
            patch("app.main._check_redis", side_effect=healthy),
            patch("app.main._check_minio", side_effect=healthy),
        ):
            ready, checks = await _readiness_status()

        self.assertTrue(ready)
        self.assertEqual(checks, {"database": "ok", "redis": "ok", "minio": "ok"})

    async def test_failed_dependency_marks_service_unavailable(self):
        async def healthy():
            return None

        async def unavailable():
            raise RuntimeError("offline")

        with (
            patch("app.main._check_database", side_effect=healthy),
            patch("app.main._check_redis", side_effect=unavailable),
            patch("app.main._check_minio", side_effect=healthy),
        ):
            ready, checks = await _readiness_status()

        self.assertFalse(ready)
        self.assertEqual(checks["redis"], "unavailable")


class ExternalUrlSecurityTests(unittest.TestCase):
    def test_rejects_plain_http(self):
        with self.assertRaisesRegex(RuntimeError, "不安全"):
            validate_external_media_url("http://example.aliyuncs.com/file.mp4")

    def test_rejects_unapproved_host(self):
        with self.assertRaisesRegex(RuntimeError, "允许列表"):
            validate_external_media_url("https://example.com/file.mp4")

    def test_rejects_loopback_even_when_host_is_allowlisted(self):
        fake_settings = SimpleNamespace(ai_media_allowed_host_list=["127.0.0.1"])
        with patch("app.utils.network_security.get_settings", return_value=fake_settings):
            with self.assertRaisesRegex(RuntimeError, "不安全的网络"):
                validate_external_media_url("https://127.0.0.1/file.mp4")


if __name__ == "__main__":
    unittest.main()
