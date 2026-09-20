"""MVP 固定后台角色与权限。"""

from typing import Final


ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "super_admin": frozenset({
        "admin.manage",
        "dashboard.read",
        "users.read",
        "users.pii.read",
        "quota.adjust",
        "subscription.grant_internal",
        "jobs.read",
        "jobs.payload.read",
        "jobs.retry",
        "jobs.cancel",
        "billing.read",
        "pricing.read",
        "pricing.write",
        "pricing.publish",
        "wallet.read",
        "wallet.adjust",
        "pass.manage",
        "subscription.reconcile",
        "invoices.handle",
        "audit.read",
    }),
    "operator": frozenset({
        "dashboard.read",
        "users.read",
        "users.pii.read",
        "quota.adjust",
        "jobs.read",
        "jobs.payload.read",
        "jobs.retry",
        "jobs.cancel",
        "billing.read",
        "pricing.read",
        "pricing.write",
        "wallet.read",
        "wallet.adjust",
        "pass.manage",
    }),
    "finance": frozenset({
        "dashboard.read",
        "users.read",
        "billing.read",
        "pricing.read",
        "pricing.publish",
        "wallet.read",
        "subscription.reconcile",
        "invoices.handle",
        "audit.read",
    }),
}


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for_role(role)
