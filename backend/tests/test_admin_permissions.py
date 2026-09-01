import unittest

from app.admin.permissions import permissions_for_role, role_has_permission


class AdminPermissionMatrixTests(unittest.TestCase):
    def test_super_admin_has_all_mvp_mutations(self):
        for permission in (
            "quota.adjust", "subscription.grant_internal", "jobs.retry", "jobs.cancel",
            "subscription.reconcile", "invoices.handle", "audit.read",
        ):
            with self.subTest(permission=permission):
                self.assertTrue(role_has_permission("super_admin", permission))

    def test_operator_cannot_change_subscriptions_or_invoices(self):
        self.assertTrue(role_has_permission("operator", "jobs.retry"))
        self.assertTrue(role_has_permission("operator", "quota.adjust"))
        self.assertFalse(role_has_permission("operator", "subscription.reconcile"))
        self.assertFalse(role_has_permission("operator", "invoices.handle"))

    def test_finance_cannot_read_payload_or_control_jobs(self):
        self.assertTrue(role_has_permission("finance", "invoices.handle"))
        self.assertFalse(role_has_permission("finance", "jobs.payload.read"))
        self.assertFalse(role_has_permission("finance", "jobs.cancel"))

    def test_unknown_role_has_no_permissions(self):
        self.assertEqual(permissions_for_role("unknown"), frozenset())


if __name__ == "__main__":
    unittest.main()
