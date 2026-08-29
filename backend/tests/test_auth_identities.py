import unittest

from app.services.auth_identities import (
    normalize_email_identity,
    normalize_phone_identity,
    phone_from_identity,
    wechat_identity_identifier,
)


class AuthIdentityNormalizationTests(unittest.TestCase):
    def test_email_is_trimmed_and_lowercased(self):
        self.assertEqual(normalize_email_identity("  User@Example.COM "), "user@example.com")

    def test_mainland_phone_is_normalized_to_e164(self):
        self.assertEqual(normalize_phone_identity("18888888888"), "+8618888888888")
        self.assertEqual(normalize_phone_identity("+86 188-8888-8888"), "+8618888888888")
        self.assertEqual(phone_from_identity("+8618888888888"), "18888888888")

    def test_invalid_phone_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "11 位手机号"):
            normalize_phone_identity("12345")

    def test_wechat_prefers_unionid_and_falls_back_to_openid(self):
        self.assertEqual(
            wechat_identity_identifier("union-123", "openid-123"),
            "unionid:union-123",
        )
        self.assertEqual(
            wechat_identity_identifier(None, "openid-123"),
            "openid:legacy:openid-123",
        )
        self.assertEqual(
            wechat_identity_identifier(None, "openid-123", "wx-app-1"),
            "openid:wx-app-1:openid-123",
        )


if __name__ == "__main__":
    unittest.main()
