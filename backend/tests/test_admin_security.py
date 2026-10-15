import io
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.admin.security import (
    ADMIN_AUDIENCE,
    ADMIN_ACCESS_TYPE,
    as_utc,
    create_admin_access_token,
    decode_admin_access_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    print_totp_qr,
    totp_code,
    totp_provisioning_uri,
    totp_qr_ascii,
    verify_totp,
)


class AdminTotpTests(unittest.TestCase):
    # RFC 6238 SHA-1 secret. The project intentionally exposes six digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_known_totp_value(self):
        self.assertEqual(totp_code(self.secret, at_time=59), "287082")
        self.assertTrue(verify_totp(self.secret, "287082", at_time=59, window=0))
        self.assertFalse(verify_totp(self.secret, "287083", at_time=59, window=0))

    def test_mfa_secret_encryption_roundtrip(self):
        encrypted = encrypt_mfa_secret(self.secret)
        self.assertNotIn(self.secret, encrypted)
        self.assertEqual(decrypt_mfa_secret(encrypted), self.secret)

    def test_naive_database_datetime_is_normalized_to_utc(self):
        value = datetime(2026, 9, 1, 12, 0, 0)
        self.assertEqual(as_utc(value), value.replace(tzinfo=timezone.utc))

    def test_totp_qr_ascii_is_terminal_only_and_scannable_shape(self):
        uri = totp_provisioning_uri("JBSWY3DPEHPK3PXP", "admin@example.com")
        rendered = totp_qr_ascii(uri)

        self.assertNotIn(uri, rendered)
        self.assertNotIn("JBSWY3DPEHPK3PXP", rendered)
        self.assertGreater(len(rendered.splitlines()), 20)
        self.assertIn("█", rendered)

    def test_totp_qr_uses_fixed_colors_for_interactive_terminal(self):
        class TtyBuffer(io.StringIO):
            def isatty(self):
                return True

        output = TtyBuffer()
        print_totp_qr(
            totp_provisioning_uri("JBSWY3DPEHPK3PXP", "admin@example.com"),
            out=output,
        )

        self.assertIn("\x1b[48;5;232m", output.getvalue())
        self.assertIn("\x1b[38;5;255m", output.getvalue())
        self.assertIn("\x1b[0m", output.getvalue())


class AdminJwtTests(unittest.TestCase):
    def test_admin_token_uses_separate_type_and_audience(self):
        with patch("app.admin.security._admin_jwt_secret", return_value="admin-test-secret" * 4):
            token = create_admin_access_token("admin-1", "session-1", 3)
            payload = decode_admin_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["aud"], ADMIN_AUDIENCE)
        self.assertEqual(payload["type"], ADMIN_ACCESS_TYPE)
        self.assertEqual(payload["ver"], 3)

    def test_ordinary_user_token_is_rejected(self):
        import jwt

        with patch("app.admin.security._admin_jwt_secret", return_value="admin-test-secret" * 4):
            token = jwt.encode(
                {"sub": "user-1", "type": "access", "aud": "videox-user"},
                "admin-test-secret" * 4,
                algorithm="HS256",
            )
            self.assertIsNone(decode_admin_access_token(token))


if __name__ == "__main__":
    unittest.main()
