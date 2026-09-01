"""运营后台用户列表、身份、用量和业务摘要。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.audit import validate_idempotent_target, write_admin_audit
from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.redaction import mask_email, mask_phone
from app.admin.schemas import ReasonRequest
from app.database import get_db
from app.models.asset import Asset
from app.models.admin import AdminAuditLog, QuotaAdjustment
from app.models.invoice import Invoice
from app.models.job import Job
from app.models.order import Order
from app.models.project import Project
from app.models.user import User, UserIdentity
from app.models.subscription import SubscriptionEvent
from app.models.user import Membership
from app.services.quotas import (
    ACTIVE_RESERVATION_STATUSES,
    QuotaType,
    active_quota_adjustment_amount,
    synchronize_user_usage,
)
from app.services.subscriptions import ensure_user_subscription


router = APIRouter()


class QuotaAdjustmentRequest(BaseModel):
    quota_type: QuotaType
    amount: int = Field(..., gt=0, le=1000000)
    expires_at: datetime | None = None
    related_job_id: str | None = Field(None, max_length=64)
    reason: str = Field(..., min_length=3, max_length=2000)


class InternalSubscriptionRequest(BaseModel):
    membership_id: str = Field(..., min_length=1, max_length=50)
    ends_at: datetime
    reason: str = Field(..., min_length=3, max_length=2000)


def _subscription_snapshot(subscription) -> dict:
    return {
        "membership_id": subscription.membership_id,
        "status": subscription.status,
        "billing_cycle": subscription.billing_cycle,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "provider": subscription.provider,
        "latest_order_id": subscription.latest_order_id,
    }


def _mask_identity(identity: UserIdentity) -> str:
    if identity.provider == "email":
        return mask_email(identity.identifier)
    if identity.provider == "phone":
        return mask_phone(identity.identifier)
    return "微信身份"


async def _user_counts(db: AsyncSession, user_id: str) -> dict[str, int]:
    project_count = (await db.execute(select(func.count(Project.id)).where(Project.owner_id == user_id))).scalar() or 0
    asset_count = (await db.execute(select(func.count(Asset.id)).where(Asset.owner_id == user_id, Asset.deleted_at.is_(None)))).scalar() or 0
    failed_since = datetime.now(timezone.utc) - timedelta(days=30)
    failed_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.owner_id == user_id, Job.status == "FAILED", Job.updated_at >= failed_since
            )
        )
    ).scalar() or 0
    return {"projects": int(project_count), "assets": int(asset_count), "failed_jobs_30d": int(failed_jobs)}


@router.get("")
async def list_users(
    q: str = Query("", max_length=200),
    membership_id: str = Query(""),
    subscription_status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc)$"),
    _: AdminPrincipal = Depends(require_admin_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).options(
        selectinload(User.identities),
        selectinload(User.membership),
        selectinload(User.subscription),
    )
    if q.strip():
        term = q.strip()
        prefix = f"{term}%"
        query = query.where(
            or_(
                User.id == term,
                User.name.ilike(prefix),
                User.email.ilike(prefix),
                User.id.in_(select(UserIdentity.user_id).where(UserIdentity.identifier.ilike(prefix))),
            )
        )
    if membership_id:
        query = query.where(User.membership_id == membership_id)
    if subscription_status:
        from app.models.subscription import Subscription
        query = query.join(Subscription, Subscription.user_id == User.id).where(
            Subscription.status == subscription_status
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    ordering = User.created_at.asc() if sort == "created_asc" else User.created_at.desc()
    users = (
        await db.execute(
            query.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().unique().all()
    items = []
    for user in users:
        counts = await _user_counts(db, user.id)
        identities = user.identities or []
        last_login = max((item.last_login_at for item in identities if item.last_login_at), default=None)
        items.append({
            "id": user.id,
            "name": user.name,
            "email": mask_email(user.email),
            "identities": [
                {"provider": item.provider, "identifier": _mask_identity(item)} for item in identities
            ],
            "membership": user.membership.name if user.membership else None,
            "membership_id": user.membership_id,
            "subscription_status": user.subscription.status if user.subscription else None,
            "last_login_at": last_login,
            "created_at": user.created_at,
            **counts,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size, "sort": sort}


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    _: AdminPrincipal = Depends(require_admin_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.identities),
                selectinload(User.membership),
                selectinload(User.subscription),
                selectinload(User.usage),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    counts = await _user_counts(db, user.id)
    reservations = (
        await db.execute(
            select(Job.quota_type, func.coalesce(func.sum(Job.quota_amount), 0))
            .where(
                Job.owner_id == user.id,
                Job.status.in_(ACTIVE_RESERVATION_STATUSES),
                Job.quota_type.is_not(None),
            )
            .group_by(Job.quota_type)
        )
    ).all()
    now = datetime.now(timezone.utc)
    adjustment_totals = {
        quota_type: await active_quota_adjustment_amount(db, user.id, quota_type, now=now)
        for quota_type in ("processing_seconds", "ai_image", "ai_video", "export")
    }
    adjustment_history = (
        await db.execute(
            select(QuotaAdjustment)
            .where(QuotaAdjustment.user_id == user.id)
            .order_by(QuotaAdjustment.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    recent_jobs = (
        await db.execute(
            select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).limit(10)
        )
    ).scalars().all()
    recent_projects = (
        await db.execute(
            select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()).limit(5)
        )
    ).scalars().all()
    recent_orders = (
        await db.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(10)
        )
    ).scalars().all()
    return {
        "id": user.id,
        "name": user.name,
        "email": mask_email(user.email),
        "created_at": user.created_at,
        "identities": [
            {
                "id": item.id,
                "provider": item.provider,
                "identifier": _mask_identity(item),
                "verified_at": item.verified_at,
                "last_login_at": item.last_login_at,
            }
            for item in user.identities
        ],
        "membership": {
            "id": user.membership.id,
            "name": user.membership.name,
            "processing_minutes": user.membership.processing_minutes,
            "ai_image_quota": user.membership.ai_image_quota,
            "ai_video_quota": user.membership.ai_video_quota,
            "storage_gb": user.membership.storage_gb,
            "export_quota": user.membership.export_quota,
        } if user.membership else None,
        "subscription": {
            "id": user.subscription.id,
            "status": user.subscription.status,
            "billing_cycle": user.subscription.billing_cycle,
            "current_period_start": user.subscription.current_period_start,
            "current_period_end": user.subscription.current_period_end,
            "provider": user.subscription.provider,
            "latest_order_id": user.subscription.latest_order_id,
        } if user.subscription else None,
        "usage": {
            "processing_seconds_used": user.usage.processing_seconds_used,
            "ai_image_used": user.usage.ai_image_used,
            "ai_video_used": user.usage.ai_video_used,
            "storage_used_mb": user.usage.storage_used_mb,
            "export_used": user.usage.export_used,
            "billing_cycle_start": user.usage.billing_cycle_start,
            "billing_cycle_end": user.usage.billing_cycle_end,
        } if user.usage else None,
        "reserved": {str(quota_type): int(amount) for quota_type, amount in reservations},
        "quota_adjustments": adjustment_totals,
        "quota_adjustment_history": [
            {
                "id": item.id,
                "quota_type": item.quota_type,
                "amount": item.amount,
                "effective_at": item.effective_at,
                "expires_at": item.expires_at,
                "reason": item.reason,
                "related_job_id": item.related_job_id,
                "created_at": item.created_at,
            }
            for item in adjustment_history
        ],
        "counts": counts,
        "recent_projects": [
            {"id": item.id, "name": item.name, "status": item.status, "updated_at": item.updated_at}
            for item in recent_projects
        ],
        "recent_jobs": [
            {"id": item.id, "name": item.name, "type": item.type, "status": item.status, "stage": item.stage, "updated_at": item.updated_at}
            for item in recent_jobs
        ],
        "recent_orders": [
            {"id": item.id, "membership_name": item.membership_name, "amount": item.amount, "status": item.status, "created_at": item.created_at, "paid_at": item.paid_at}
            for item in recent_orders
        ],
    }


@router.post("/{user_id}/reveal-identities")
async def reveal_identities(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("users.pii.read")),
    db: AsyncSession = Depends(get_db),
):
    identities = (
        await db.execute(select(UserIdentity).where(UserIdentity.user_id == user_id).order_by(UserIdentity.created_at))
    ).scalars().all()
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="USER_IDENTITIES_REVEAL",
        target_type="user",
        target_id=user_id,
        reason=payload.reason,
        after_data={"providers": [item.provider for item in identities]},
    )
    return {
        "user_id": user_id,
        "legacy_email": user.email,
        "identities": [
            {"provider": item.provider, "identifier": item.identifier, "verified_at": item.verified_at, "last_login_at": item.last_login_at}
            for item in identities
        ],
    }


@router.post("/{user_id}/quota-adjustments", status_code=201)
async def create_quota_adjustment(
    user_id: str,
    payload: QuotaAdjustmentRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("quota.adjust")),
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(
            select(QuotaAdjustment).where(
                QuotaAdjustment.admin_user_id == principal.user.id,
                QuotaAdjustment.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(
                status_code=409,
                detail="该幂等键已用于其他用户，请生成新的幂等键后重试",
            )
        return {
            "id": existing.id,
            "user_id": existing.user_id,
            "quota_type": existing.quota_type,
            "amount": existing.amount,
            "expires_at": existing.expires_at,
            "created_at": existing.created_at,
            "idempotent_replay": True,
        }
    user = (
        await db.execute(
            select(User).where(User.id == user_id).options(
                selectinload(User.membership), selectinload(User.subscription), selectinload(User.usage)
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    usage = await synchronize_user_usage(db, user, for_update=True)
    expires_at = payload.expires_at or usage.billing_cycle_end
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="额度补偿到期时间必须晚于当前时间")
    related_job = None
    if payload.related_job_id:
        related_job = await db.get(Job, payload.related_job_id)
        if not related_job or related_job.owner_id != user.id:
            raise HTTPException(status_code=422, detail="关联任务不存在或不属于该用户")
    before_amount = await active_quota_adjustment_amount(
        db, user.id, payload.quota_type, now=datetime.now(timezone.utc)
    )
    adjustment = QuotaAdjustment(
        user_id=user.id,
        quota_type=payload.quota_type,
        amount=payload.amount,
        expires_at=expires_at,
        reason=payload.reason.strip(),
        related_job_id=related_job.id if related_job else None,
        admin_user_id=principal.user.id,
        idempotency_key=idempotency_key,
    )
    db.add(adjustment)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="QUOTA_ADJUSTMENT_CREATE",
        target_type="user",
        target_id=user.id,
        reason=payload.reason,
        before_data={"quota_type": payload.quota_type, "active_adjustment": before_amount},
        after_data={
            "adjustment_id": adjustment.id,
            "quota_type": payload.quota_type,
            "amount": payload.amount,
            "active_adjustment": before_amount + payload.amount,
            "expires_at": expires_at.isoformat(),
            "related_job_id": adjustment.related_job_id,
        },
        idempotency_key=idempotency_key,
    )
    return {
        "id": adjustment.id,
        "user_id": adjustment.user_id,
        "quota_type": adjustment.quota_type,
        "amount": adjustment.amount,
        "expires_at": adjustment.expires_at,
        "created_at": adjustment.created_at,
        "idempotent_replay": False,
    }


@router.post("/{user_id}/internal-subscription")
async def grant_internal_subscription(
    user_id: str,
    payload: InternalSubscriptionRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("subscription.grant_internal")),
    db: AsyncSession = Depends(get_db),
):
    existing_audit = (
        await db.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.admin_user_id == principal.user.id,
                AdminAuditLog.action == "INTERNAL_SUBSCRIPTION_GRANT",
                AdminAuditLog.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing_audit:
        validate_idempotent_target(
            existing_audit, target_type="user", target_id=user_id
        )
        prior = dict(existing_audit.after_data or {})
        event_id = prior.pop("subscription_event_id", None)
        return {
            "user_id": user_id,
            "subscription": prior,
            "event_id": event_id,
            "idempotent_replay": True,
        }
    user = (
        await db.execute(
            select(User).where(User.id == user_id).options(
                selectinload(User.membership), selectinload(User.subscription), selectinload(User.usage)
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    membership = await db.get(Membership, payload.membership_id)
    if not membership or membership.rank <= 0:
        raise HTTPException(status_code=422, detail="内部授权必须选择有效的付费会员方案")
    now = datetime.now(timezone.utc)
    ends_at = payload.ends_at if payload.ends_at.tzinfo else payload.ends_at.replace(tzinfo=timezone.utc)
    if ends_at <= now:
        raise HTTPException(status_code=422, detail="内部授权结束时间必须晚于当前时间")
    if ends_at > now + timedelta(days=90):
        raise HTTPException(status_code=422, detail="MVP 内部授权最长为 90 天")
    subscription = await ensure_user_subscription(db, user, for_update=True)
    if (
        subscription.status == "active"
        and subscription.provider == "alipay"
        and subscription.current_period_end
        and subscription.current_period_end > now
    ):
        raise HTTPException(status_code=409, detail="用户当前有生效中的付费订阅，不能用内部授权覆盖")
    before = _subscription_snapshot(subscription)
    subscription.membership_id = membership.id
    subscription.status = "internal"
    subscription.billing_cycle = "permanent"
    subscription.current_period_start = now
    subscription.current_period_end = ends_at
    subscription.auto_renew = False
    subscription.cancel_at_period_end = False
    subscription.provider = "admin_internal"
    subscription.provider_subscription_id = None
    subscription.latest_order_id = None
    subscription.updated_at = now
    user.membership_id = membership.id
    user.membership = membership
    await synchronize_user_usage(db, user, now=now, for_update=True)
    after = _subscription_snapshot(subscription)
    event = SubscriptionEvent(
        user_id=user.id,
        subscription_id=subscription.id,
        event_type="internal_granted",
        before_data=before,
        after_data=after,
        admin_user_id=principal.user.id,
        reason=payload.reason.strip(),
    )
    db.add(event)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="INTERNAL_SUBSCRIPTION_GRANT",
        target_type="user",
        target_id=user.id,
        reason=payload.reason,
        before_data=before,
        after_data={**after, "subscription_event_id": event.id},
        idempotency_key=idempotency_key,
    )
    return {
        "user_id": user.id,
        "subscription": after,
        "event_id": event.id,
        "idempotent_replay": False,
    }
