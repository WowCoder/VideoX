"""独立运营后台登录、刷新、退出和当前管理员。"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import write_admin_audit
from app.admin.dependencies import AdminPrincipal, get_current_admin
from app.admin.permissions import permissions_for_role
from app.admin.schemas import (
    AdminAuthResponse,
    AdminLoginRequest,
    AdminMessageResponse,
    AdminOut,
    AdminTokenResponse,
)
from app.admin.security import (
    create_admin_access_token,
    as_utc,
    decrypt_mfa_secret,
    generate_refresh_token,
    hash_refresh_token,
    session_expiry,
    verify_totp,
)
from app.config import get_settings
from app.database import get_db
from app.models.admin import AdminSession, AdminUser
from app.security import verify_password


router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _admin_out(admin: AdminUser) -> AdminOut:
    return AdminOut(
        id=admin.id,
        email=admin.email,
        name=admin.name,
        role=admin.role,
        status=admin.status,
        permissions=sorted(permissions_for_role(admin.role)),
        last_login_at=admin.last_login_at,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.admin_refresh_cookie_name,
        value=token,
        max_age=settings.admin_session_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="strict" if settings.environment.lower() == "production" else "lax",
        path="/api/admin/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.admin_refresh_cookie_name,
        path="/api/admin/auth",
        secure=settings.environment.lower() == "production",
        httponly=True,
        samesite="strict" if settings.environment.lower() == "production" else "lax",
    )


async def _record_failed_login(
    db: AsyncSession,
    admin: AdminUser,
    request: Request,
) -> None:
    admin.failed_login_count += 1
    if admin.failed_login_count >= settings.admin_login_max_attempts:
        admin.locked_until = _utcnow() + timedelta(minutes=settings.admin_login_lock_minutes)
        admin.failed_login_count = 0
    await write_admin_audit(
        db,
        admin=admin,
        request=request,
        action="ADMIN_LOGIN",
        target_type="admin_user",
        target_id=admin.id,
        status="failed",
        error_message="管理员认证信息错误",
    )
    await db.commit()


@router.post("/login", response_model=AdminAuthResponse)
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    normalized_email = str(payload.email).strip().lower()
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.email == normalized_email).with_for_update())
    ).scalar_one_or_none()
    generic_error = HTTPException(status_code=401, detail="管理员账号或验证信息错误")
    now = _utcnow()
    if not admin:
        logger.warning(
            "Unknown administrator login rejected ip=%s email_hash=%s",
            request.client.host if request.client else "unknown",
            hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()[:16],
        )
        raise generic_error
    if admin.status != "active":
        await _record_failed_login(db, admin, request)
        raise generic_error
    if admin.locked_until and as_utc(admin.locked_until) > now:
        raise HTTPException(status_code=423, detail="管理员账号已临时锁定，请稍后重试")
    if admin.locked_until and as_utc(admin.locked_until) <= now:
        admin.locked_until = None
        admin.failed_login_count = 0

    password_valid = verify_password(payload.password, admin.password_hash)
    otp_valid = False
    if password_valid and admin.mfa_enabled:
        try:
            otp_valid = verify_totp(decrypt_mfa_secret(admin.mfa_secret_encrypted), payload.otp)
        except RuntimeError:
            otp_valid = False
    elif password_valid:
        otp_valid = True
    if not password_valid or not otp_valid:
        await _record_failed_login(db, admin, request)
        raise generic_error

    refresh_token = generate_refresh_token()
    session = AdminSession(
        admin_user_id=admin.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        token_version=admin.token_version,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent", "")[:500] or None,
        expires_at=session_expiry(),
    )
    db.add(session)
    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = now
    admin.last_login_ip = request.client.host if request.client else None
    await db.flush()
    await write_admin_audit(
        db,
        admin=admin,
        request=request,
        action="ADMIN_LOGIN",
        target_type="admin_session",
        target_id=session.id,
        after_data={"role": admin.role},
    )
    access_token = create_admin_access_token(admin.id, session.id, admin.token_version)
    _set_refresh_cookie(response, refresh_token)
    return AdminAuthResponse(
        admin=_admin_out(admin),
        access_token=access_token,
        expires_in=settings.admin_access_expire_minutes * 60,
    )


@router.post("/refresh", response_model=AdminTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(settings.admin_refresh_cookie_name, "")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="管理员刷新会话不存在")
    token_hash = hash_refresh_token(refresh_token)
    session = (
        await db.execute(
            select(AdminSession)
            .join(AdminUser)
            .where(AdminSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = _utcnow()
    if not session:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="管理员刷新会话无效")
    admin = await db.get(AdminUser, session.admin_user_id)
    if (
        not admin
        or admin.status != "active"
        or session.revoked_at is not None
        or as_utc(session.expires_at) <= now
        or session.token_version != admin.token_version
    ):
        session.revoked_at = session.revoked_at or now
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="管理员刷新会话已失效")

    new_refresh_token = generate_refresh_token()
    session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    session.last_seen_at = now
    session.ip_address = request.client.host if request.client else session.ip_address
    session.user_agent = request.headers.get("User-Agent", "")[:500] or session.user_agent
    _set_refresh_cookie(response, new_refresh_token)
    return AdminTokenResponse(
        access_token=create_admin_access_token(admin.id, session.id, admin.token_version),
        expires_in=settings.admin_access_expire_minutes * 60,
    )


@router.post("/logout", response_model=AdminMessageResponse)
async def logout(
    request: Request,
    response: Response,
    principal: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    principal.session.revoked_at = _utcnow()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="ADMIN_LOGOUT",
        target_type="admin_session",
        target_id=principal.session.id,
    )
    _clear_refresh_cookie(response)
    return AdminMessageResponse(message="已安全退出运营后台")


@router.post("/logout-all", response_model=AdminMessageResponse)
async def logout_all(
    request: Request,
    response: Response,
    principal: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    now = _utcnow()
    await db.execute(
        update(AdminSession)
        .where(AdminSession.admin_user_id == principal.user.id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    principal.user.token_version += 1
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="ADMIN_LOGOUT_ALL",
        target_type="admin_user",
        target_id=principal.user.id,
    )
    _clear_refresh_cookie(response)
    return AdminMessageResponse(message="所有管理员会话均已退出")


@router.get("/me", response_model=AdminOut)
async def me(principal: AdminPrincipal = Depends(get_current_admin)):
    return _admin_out(principal.user)
