"""运营后台审计日志只读查询。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.database import get_db
from app.models.admin import AdminAuditLog, AdminUser


router = APIRouter()


@router.get("")
async def list_audit_logs(
    action: str = Query(""),
    target_type: str = Query(""),
    target_id: str = Query(""),
    status_filter: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc)$"),
    _: AdminPrincipal = Depends(require_admin_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(AdminAuditLog, AdminUser).join(AdminUser, AdminUser.id == AdminAuditLog.admin_user_id)
    if action:
        query = query.where(AdminAuditLog.action == action)
    if target_type:
        query = query.where(AdminAuditLog.target_type == target_type)
    if target_id:
        query = query.where(AdminAuditLog.target_id == target_id)
    if status_filter:
        query = query.where(AdminAuditLog.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    ordering = AdminAuditLog.created_at.asc() if sort == "created_asc" else AdminAuditLog.created_at.desc()
    rows = (
        await db.execute(
            query.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": audit.id,
                "admin": {"id": admin.id, "name": admin.name, "email": admin.email, "role": admin.role},
                "action": audit.action,
                "target_type": audit.target_type,
                "target_id": audit.target_id,
                "reason": audit.reason,
                "before_data": audit.before_data,
                "after_data": audit.after_data,
                "request_id": audit.request_id,
                "ip_address": audit.ip_address,
                "status": audit.status,
                "error_message": audit.error_message,
                "created_at": audit.created_at,
            }
            for audit, admin in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "sort": sort,
    }
