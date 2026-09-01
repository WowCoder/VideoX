import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from app.admin.audit import validate_idempotent_target
from app.admin.redaction import mask_email, mask_phone, redact_mapping
from app.api.admin.users import InternalSubscriptionRequest, QuotaAdjustmentRequest
from app.models.admin import AdminAuditLog, QuotaAdjustment


class AdminOperationContractTests(unittest.TestCase):
    def test_quota_adjustment_request_is_positive_only(self):
        with self.assertRaises(ValidationError):
            QuotaAdjustmentRequest(quota_type="ai_image", amount=0, reason="测试补偿")
        request = QuotaAdjustmentRequest(quota_type="ai_image", amount=2, reason="测试补偿")
        self.assertEqual(request.amount, 2)

    def test_quota_adjustment_database_has_positive_constraint(self):
        names = {constraint.name for constraint in QuotaAdjustment.__table__.constraints}
        self.assertIn("ck_quota_adjustments_positive", names)

    def test_internal_subscription_request_accepts_bounded_payload_shape(self):
        request = InternalSubscriptionRequest(
            membership_id="membership-pro",
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
            reason="客户问题补偿",
        )
        self.assertEqual(request.membership_id, "membership-pro")

    def test_idempotency_key_cannot_be_replayed_for_another_target(self):
        audit = AdminAuditLog(
            admin_user_id="admin-1", action="JOB_RETRY", target_type="job", target_id="job-1",
            reason="retry", idempotency_key="key-12345678",
        )
        validate_idempotent_target(audit, target_type="job", target_id="job-1")
        with self.assertRaises(HTTPException) as context:
            validate_idempotent_target(audit, target_type="job", target_id="job-2")
        self.assertEqual(context.exception.status_code, 409)

    def test_sensitive_values_are_masked_and_nested_secrets_redacted(self):
        self.assertEqual(mask_email("operator@example.com"), "op***@example.com")
        self.assertTrue(mask_phone("13800138000").startswith("138"))
        payload = redact_mapping({
            "prompt": "safe text",
            "api_key": "secret",
            "nested": {"authorization": "Bearer token", "asset_id": "asset-1"},
        })
        self.assertNotEqual(payload["api_key"], "secret")
        self.assertNotEqual(payload["nested"]["authorization"], "Bearer token")
        self.assertEqual(payload["nested"]["asset_id"], "asset-1")


if __name__ == "__main__":
    unittest.main()
