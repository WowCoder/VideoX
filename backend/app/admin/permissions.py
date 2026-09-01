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
    }),
    "finance": frozenset({
        "dashboard.read",
        "users.read",
        "billing.read",
        "subscription.reconcile",
        "invoices.handle",
        "audit.read",
    }),
}


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for_role(role)
