"""会员周期用量同步、任务额度准入与成功结算。"""

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.models.billing import CreditHold
from app.models.admin import QuotaAdjustment
from app.models.subscription import Subscription
from app.models.user import Membership, Usage, User
from app.services.subscriptions import as_utc, reconcile_user_subscription, utcnow
from app.services.billing_v2 import capture_hold, release_hold


QuotaType = Literal["processing_seconds", "ai_image", "ai_video", "export"]
ACTIVE_RESERVATION_STATUSES = {"QUEUED", "RUNNING", "PAUSED"}


@dataclass(frozen=True)
class QuotaSnapshot:
    quota_type: QuotaType
    limit: int
    used: int
    reserved: int
    requested: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used - self.reserved)


class QuotaExceededError(ValueError):
    def __init__(self, snapshot: QuotaSnapshot):
        super().__init__("会员额度不足")
        self.snapshot = snapshot


def _add_anchor_months(anchor: datetime, months: int) -> datetime:
    anchor = as_utc(anchor)
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def monthly_usage_period(anchor: datetime, now: datetime) -> tuple[datetime, datetime]:
    """以订阅锚点计算自然月周期，并保持月末锚点不漂移。"""
    anchor = as_utc(anchor)
    now = as_utc(now)
    if now < anchor:
        return anchor, _add_anchor_months(anchor, 1)

    month_offset = (now.year - anchor.year) * 12 + now.month - anchor.month
    start = _add_anchor_months(anchor, month_offset)
    if start > now:
        month_offset -= 1
        start = _add_anchor_months(anchor, month_offset)
    return start, _add_anchor_months(anchor, month_offset + 1)


def expected_usage_period(
    subscription: Subscription,
    now: datetime,
) -> tuple[datetime, datetime]:
    """付费、免费和测试授权会员均按月刷新用量额度。"""
    anchor = subscription.current_period_start
    if subscription.status == "expired" and subscription.current_period_end is not None:
        anchor = subscription.current_period_end
    return monthly_usage_period(anchor, now)


def _period_matches(usage: Usage, start: datetime, end: datetime) -> bool:
    return (
        as_utc(usage.billing_cycle_start) == as_utc(start)
        and as_utc(usage.billing_cycle_end) == as_utc(end)
    )


def reset_periodic_usage(usage: Usage, start: datetime, end: datetime) -> None:
    usage.processing_seconds_used = 0
    usage.ai_image_used = 0
    usage.ai_video_used = 0
    usage.export_used = 0
    usage.billing_cycle_start = as_utc(start)
    usage.billing_cycle_end = as_utc(end)


async def synchronize_user_usage(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    for_update: bool = False,
) -> Usage:
    """确保用户用量记录属于当前月度周期；存储用量不随周期重置。"""
    now = as_utc(now or utcnow())
    subscription = user.subscription or await reconcile_user_subscription(db, user, now=now)

    query = select(Usage).where(Usage.user_id == user.id)
    if for_update:
        query = query.with_for_update()
    usage = (await db.execute(query)).scalar_one_or_none()
    if usage is None:
        usage = Usage(user_id=user.id)
        db.add(usage)
        await db.flush()

    start, end = expected_usage_period(subscription, now)
    if not _period_matches(usage, start, end):
        reset_periodic_usage(usage, start, end)
        await db.flush()
    user.usage = usage
    return usage


async def _locked_billing_context(
    db: AsyncSession,
    user_id: str,
    *,
    now: datetime,
) -> tuple[User, Membership, Usage]:
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.membership), selectinload(User.subscription))
            .with_for_update()
        )
    ).scalar_one()
    await reconcile_user_subscription(db, user, now=now)
    usage = await synchronize_user_usage(db, user, now=now, for_update=True)
    membership = user.membership
    if membership is None:
        membership = (
            await db.execute(select(Membership).where(Membership.id == user.membership_id))
        ).scalar_one()
        user.membership = membership
    return user, membership, usage


def _quota_limit(membership: Membership, quota_type: QuotaType) -> int:
    if quota_type == "processing_seconds":
        return max(0, membership.processing_minutes * 60)
    if quota_type == "ai_image":
        return max(0, membership.ai_image_quota)
    if quota_type == "ai_video":
        return max(0, membership.ai_video_quota)
    return max(0, membership.export_quota)


async def active_quota_adjustment_amount(
    db: AsyncSession,
    user_id: str,
    quota_type: QuotaType,
    *,
    now: datetime,
) -> int:
    """统计当前生效且尚未过期的正向额度补偿。"""
    amount = (
        await db.execute(
            select(func.coalesce(func.sum(QuotaAdjustment.amount), 0)).where(
                QuotaAdjustment.user_id == user_id,
                QuotaAdjustment.quota_type == quota_type,
                QuotaAdjustment.effective_at <= now,
                or_(QuotaAdjustment.expires_at.is_(None), QuotaAdjustment.expires_at > now),
            )
        )
    ).scalar() or 0
    return max(0, int(amount))


def _quota_used(usage: Usage, quota_type: QuotaType) -> int:
    if quota_type == "processing_seconds":
        return max(0, usage.processing_seconds_used)
    if quota_type == "ai_image":
        return max(0, usage.ai_image_used)
    if quota_type == "ai_video":
        return max(0, usage.ai_video_used)
    return max(0, usage.export_used)


def _add_used(usage: Usage, quota_type: QuotaType, amount: int) -> None:
    if quota_type == "processing_seconds":
        usage.processing_seconds_used += amount
    elif quota_type == "ai_image":
        usage.ai_image_used += amount
    elif quota_type == "ai_video":
        usage.ai_video_used += amount
    else:
        usage.export_used += amount


async def _reserved_amount(
    db: AsyncSession,
    user_id: str,
    quota_type: QuotaType,
    *,
    exclude_job_id: str | None = None,
) -> int:
    query = (
        select(func.coalesce(func.sum(Job.quota_amount), 0))
        .select_from(Job)
        .where(
            Job.owner_id == user_id,
            Job.quota_type == quota_type,
            Job.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    )
    if exclude_job_id:
        query = query.where(Job.id != exclude_job_id)
    return int((await db.execute(query)).scalar() or 0)


async def admit_job_quota(
    db: AsyncSession,
    job: Job,
    user_id: str,
    quota_type: QuotaType,
    amount: int,
    *,
    now: datetime | None = None,
) -> QuotaSnapshot:
    """在用户行锁下检查并把新任务登记为额度预占。"""
    if amount <= 0:
        raise ValueError("任务额度必须大于 0")
    now = as_utc(now or utcnow())
    _, membership, usage = await _locked_billing_context(db, user_id, now=now)
    reserved = await _reserved_amount(db, user_id, quota_type)
    adjustment = await active_quota_adjustment_amount(db, user_id, quota_type, now=now)
    snapshot = QuotaSnapshot(
        quota_type=quota_type,
        limit=_quota_limit(membership, quota_type) + adjustment,
        used=_quota_used(usage, quota_type),
        reserved=reserved,
        requested=amount,
    )
    if snapshot.used + snapshot.reserved + amount > snapshot.limit:
        raise QuotaExceededError(snapshot)
    job.quota_type = quota_type
    job.quota_amount = amount
    return snapshot


async def readmit_existing_job_quota(
    db: AsyncSession,
    job: Job,
    user_id: str,
    *,
    now: datetime | None = None,
) -> QuotaSnapshot | None:
    """失败重试或暂停恢复时，按当前会员和周期重新确认原预占。"""
    if not job.quota_type or job.quota_amount <= 0:
        return None
    quota_type = cast(QuotaType, job.quota_type)
    now = as_utc(now or utcnow())
    _, membership, usage = await _locked_billing_context(db, user_id, now=now)
    reserved = await _reserved_amount(
        db,
        user_id,
        quota_type,
        exclude_job_id=job.id,
    )
    adjustment = await active_quota_adjustment_amount(db, user_id, quota_type, now=now)
    snapshot = QuotaSnapshot(
        quota_type=quota_type,
        limit=_quota_limit(membership, quota_type) + adjustment,
        used=_quota_used(usage, quota_type),
        reserved=reserved,
        requested=job.quota_amount,
    )
    if snapshot.used + snapshot.reserved + snapshot.requested > snapshot.limit:
        raise QuotaExceededError(snapshot)
    return snapshot


async def complete_job_success(
    db: AsyncSession,
    job_id: str,
    *,
    values: dict[str, object],
    now: datetime | None = None,
) -> bool:
    """仅允许活动任务首次成功，并在同一事务中结算其预占额度。"""
    now = as_utc(now or utcnow())
    row = (
        await db.execute(
            select(Job).where(Job.id == job_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    job = row
    owner_id = job.owner_id
    if job.status == "SUCCEEDED":
        return False
    if job.status not in {"QUEUED", "RUNNING"}:
        return False

    if job.billing_hold_id:
        captured = await capture_hold(db, job.billing_hold_id)
        hold = await db.get(CreditHold, job.billing_hold_id)
        if captured or (hold is not None and hold.status == "captured"):
            job.billed_credits = int(job.quoted_credits or 0)
        elif hold is None or hold.status != "active":
            # Hold 已被失败/取消路径释放，不能把任务错误地标记为成功。
            return False
    elif job.quota_type and job.quota_amount > 0:
        quota_type = cast(QuotaType, job.quota_type)
        _, _, usage = await _locked_billing_context(db, owner_id, now=now)
        _add_used(usage, quota_type, job.quota_amount)

    for field, value in values.items():
        setattr(job, field, value)
    job.status = "SUCCEEDED"
    job.finished_at = now
    job.error_code = None
    job.error_category = None
    job.updated_at = now
    await db.flush()
    return True


async def fail_job(
    db: AsyncSession,
    job_id: str,
    *,
    detail: str = "任务执行失败",
    stage: str = "执行失败",
    error_code: str | None = None,
    error_category: str | None = None,
    now: datetime | None = None,
) -> bool:
    """将任务置为失败并释放 V-Credits hold；可安全重复调用。"""
    now = as_utc(now or utcnow())
    row = (
        await db.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.status == "FAILED":
        return False
    if row.status in {"SUCCEEDED", "CANCELLED"}:
        return False
    if row.billing_hold_id:
        await release_hold(db, row.billing_hold_id, reason="任务失败释放")
    row.status = "FAILED"
    row.stage = stage
    row.detail = detail[:500]
    row.result = None
    row.result_detail = detail[:1000]
    row.error_code = error_code
    row.error_category = error_category
    row.finished_at = now
    row.updated_at = now
    await db.flush()
    return True
