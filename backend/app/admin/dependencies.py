"""后台管理员认证和权限依赖。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.permissions import role_has_permission
from app.admin.security import as_utc, decode_admin_access_token
from app.database import get_db
from app.models.admin import AdminSession, AdminUser


admin_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AdminPrincipal:
    user: AdminUser
    session: AdminSession


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminPrincipal:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供管理员认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_admin_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员会话无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    admin_id = str(payload.get("sub") or "")
    session_id = str(payload.get("sid") or "")
    token_version = int(payload.get("ver") or 0)
    session = (
        await db.execute(
            select(AdminSession)
            .where(AdminSession.id == session_id, AdminSession.admin_user_id == admin_id)
            .options(selectinload(AdminSession.admin_user))
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        session is None
        or session.revoked_at is not None
        or as_utc(session.expires_at) <= now
        or session.token_version != token_version
        or session.admin_user.token_version != token_version
        or session.admin_user.status != "active"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员会话已失效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AdminPrincipal(user=session.admin_user, session=session)


def require_admin_permission(permission: str):
    async def dependency(
        principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
    ) -> AdminPrincipal:
        if not role_has_permission(principal.user.role, permission):
            raise HTTPException(status_code=403, detail="当前管理员没有执行该操作的权限")
        return principal

    return dependency
