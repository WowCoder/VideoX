"""后台审计写入与请求上下文提取。"""

import uuid
from typing import Any

from fastapi import Request
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminAuditLog, AdminUser


def request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.headers.get("X-Request-ID") or f"admin-request-{uuid.uuid4().hex[:16]}",
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent", "")[:500] or None,
    }


async def write_admin_audit(
    db: AsyncSession,
    *,
    admin: AdminUser,
    request: Request,
    action: str,
    target_type: str,
    target_id: str,
    reason: str = "",
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    status: str = "succeeded",
    error_message: str = "",
) -> AdminAuditLog:
    context = request_context(request)
    audit = AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason.strip(),
        before_data=before_data or {},
        after_data=after_data or {},
        request_id=context["request_id"],
        idempotency_key=idempotency_key,
        ip_address=context["ip_address"],
        user_agent=context["user_agent"],
        status=status,
        error_message=error_message[:2000],
    )
    db.add(audit)
    await db.flush()
    return audit


def validate_idempotent_target(
    audit: AdminAuditLog,
    *,
    target_type: str,
    target_id: str,
) -> None:
    """Prevent one idempotency key from being replayed against another resource."""
    if audit.target_type != target_type or audit.target_id != target_id:
        raise HTTPException(
            status_code=409,
            detail="该幂等键已用于其他目标，请生成新的幂等键后重试",
        )


async def reserve_admin_command_audit(
    db: AsyncSession,
    *,
    admin: AdminUser,
    request: Request,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
) -> tuple[AdminAuditLog, bool]:
    """Atomically reserve a mutation and return ``(audit, is_replay)``.

    The savepoint makes concurrent requests with the same unique key converge on
    the first audit row without invalidating the outer request transaction.
    """
    existing = (
        await db.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.admin_user_id == admin.id,
                AdminAuditLog.action == action,
                AdminAuditLog.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        validate_idempotent_target(existing, target_type=target_type, target_id=target_id)
        return existing, True

    try:
        async with db.begin_nested():
            audit = await write_admin_audit(
                db,
                admin=admin,
                request=request,
                action=action,
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                idempotency_key=idempotency_key,
                status="started",
            )
    except IntegrityError:
        existing = (
            await db.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.admin_user_id == admin.id,
                    AdminAuditLog.action == action,
                    AdminAuditLog.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one()
        validate_idempotent_target(existing, target_type=target_type, target_id=target_id)
        return existing, True
    return audit, False
