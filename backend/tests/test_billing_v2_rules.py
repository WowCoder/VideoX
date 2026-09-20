from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.api.generate import ProjectOperationRequest, _media_billing_sku
from app.services.billing_v2 import (
    _account_total,
    _add_months,
    calculate_topup_credits,
    subscription_order_period_start,
    validate_plan_generation_entitlements,
)


class BillingV2RuleTests(unittest.TestCase):
    def test_operation_request_carries_confirmed_catalog_snapshot(self):
        request = ProjectOperationRequest(
            scope={"type": "project"},
            operation="generate_script",
            parameters={"prompt": "a sufficiently detailed script prompt"},
            expected_revision=3,
            pricing_catalog_id="catalog-v1",
        )
        self.assertEqual(request.pricing_catalog_id, "catalog-v1")

    def test_plan_entitlements_reject_unsupported_requests(self):
        plan = SimpleNamespace(batch_access=False, max_video_resolution="720p", max_image_resolution="1k")
        with self.assertRaisesRegex(ValueError, "批量"):
            validate_plan_generation_entitlements(plan, operation="video", batch=True)
        with self.assertRaisesRegex(ValueError, "720p"):
            validate_plan_generation_entitlements(plan, operation="video", resolution="1080p")
        with self.assertRaisesRegex(ValueError, "1k"):
            validate_plan_generation_entitlements(plan, operation="image", resolution="2k")

    def test_plan_entitlements_allow_supported_requests(self):
        plan = SimpleNamespace(batch_access=True, max_video_resolution="1080p", max_image_resolution="2k")
        validate_plan_generation_entitlements(plan, operation="video", resolution="720p", batch=True)
        validate_plan_generation_entitlements(plan, operation="image", resolution="2k")

    def test_topup_uses_package_then_membership_bonus(self):
        # ¥50 package: 5,000 × 1.02 × 1.07 = 5,457 credits.
        self.assertEqual(calculate_topup_credits(5000, 200, 700), 5457)

    def test_topup_bonus_rounds_each_layer_down(self):
        # The intermediate package result is rounded before membership bonus.
        self.assertEqual(calculate_topup_credits(101, 333, 777), 112)

    def test_media_skus_follow_model_resolution_and_duration(self):
        self.assertEqual(_media_billing_sku("generate_image", {"resolution": "1k"}, None), ("image.fast.1k", 1))
        self.assertEqual(_media_billing_sku("generate_image", {"resolution": "2k", "quality": "pro"}, None), ("image.pro.2k", 1))
        self.assertEqual(_media_billing_sku("generate_video", {"resolution": "1080p", "quality": "premium"}, {"duration_seconds": 8}), ("video.premium.1080p", 8))
        self.assertEqual(_media_billing_sku("generate_effect", {"duration_seconds": 6}, None), ("video.standard.720p", 6))

    def test_subscription_rollover_expiry_is_three_cycles(self):
        start = datetime(2026, 1, 31, tzinfo=timezone.utc)
        self.assertEqual(_add_months(start, 3), datetime(2026, 4, 30, tzinfo=timezone.utc))

    def test_renewal_credits_start_at_latest_order_window(self):
        # A monthly renewal extends Oct 30 -> Nov 30 while keeping the original
        # Sep 30 subscription anchor.  The new order may only own October's
        # window, not re-grant September's historical cycle.
        self.assertEqual(
            subscription_order_period_start(
                datetime(2026, 9, 30, tzinfo=timezone.utc),
                datetime(2026, 11, 30, tzinfo=timezone.utc),
                "monthly",
            ),
            datetime(2026, 10, 30, tzinfo=timezone.utc),
        )

    def test_annual_order_window_does_not_start_before_subscription_anchor(self):
        anchor = datetime(2026, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(
            subscription_order_period_start(anchor, datetime(2027, 9, 30, tzinfo=timezone.utc), "yearly"),
            anchor,
        )

    def test_ledger_total_includes_reserved_credits(self):
        wallet = SimpleNamespace(cached_available_credits=700, cached_reserved_credits=300)
        self.assertEqual(_account_total(wallet), 1000)


if __name__ == "__main__":
    unittest.main()
