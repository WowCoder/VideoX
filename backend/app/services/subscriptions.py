"""会员订阅周期、续费与到期降级逻辑。"""

import calendar
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.subscription import Subscription
from app.models.user import Membership, User


FREE_MEMBERSHIP_ID = "membership-free"
PAID_CYCLES = {"monthly", "yearly"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def add_billing_period(start: datetime, billing_cycle: str) -> datetime:
    """按自然月/年延长周期，并安全处理月末日期。"""
    if billing_cycle not in PAID_CYCLES:
        raise ValueError("计费周期必须是 monthly 或 yearly")
    months = 1 if billing_cycle == "monthly" else 12
    start = as_utc(start)
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def initial_subscription_values(membership_rank: int, started_at: datetime) -> dict[str, object]:
    """为旧账号或新账号生成不虚构到期时间的初始订阅。"""
    is_free = membership_rank <= 0
    return {
        "status": "active" if is_free else "internal",
        "billing_cycle": "permanent",
        "current_period_start": as_utc(started_at),
        "current_period_end": None,
        "auto_renew": False,
        "cancel_at_period_end": False,
        "provider": "system" if is_free else "internal",
    }


def renewed_period(
    *,
    current_start: datetime,
    current_end: datetime | None,
    current_status: str,
    billing_cycle: str,
    now: datetime,
) -> tuple[datetime, datetime]:
    """提前续费从现有到期日延长；已过期订阅从支付时间重新开始。"""
    now = as_utc(now)
    existing_end = as_utc(current_end) if current_end is not None else None
    if current_status == "active" and existing_end and existing_end > now:
        return as_utc(current_start), add_billing_period(existing_end, billing_cycle)
    return now, add_billing_period(now, billing_cycle)


def purchased_period(
    *,
    current_membership_id: str,
    target_membership_id: str,
    current_start: datetime,
    current_end: datetime | None,
    current_status: str,
    billing_cycle: str,
    now: datetime,
) -> tuple[datetime, datetime]:
    """计算购买后的周期：同方案续期，跨档升级从支付时间开始。"""
    now = as_utc(now)
    if current_membership_id == target_membership_id:
        return renewed_period(
            current_start=current_start,
            current_end=current_end,
            current_status=current_status,
            billing_cycle=billing_cycle,
            now=now,
        )
    return now, add_billing_period(now, billing_cycle)


async def ensure_user_subscription(
    db: AsyncSession,
    user: User,
    *,
    for_update: bool = False,
) -> Subscription:
    query = select(Subscription).where(Subscription.user_id == user.id)
    if for_update:
        query = query.with_for_update()
    subscription = (await db.execute(query)).scalar_one_or_none()
    if subscription:
        return subscription

    membership = (
        await db.execute(select(Membership).where(Membership.id == user.membership_id))
    ).scalar_one_or_none()
    values = initial_subscription_values(
        membership.rank if membership else 0,
        user.created_at or utcnow(),
    )
    subscription = Subscription(
        user_id=user.id,
        membership_id=user.membership_id,
        **values,
    )
    db.add(subscription)
    await db.flush()
    user.subscription = subscription
    return subscription


async def activate_paid_subscription(
    db: AsyncSession,
    user: User,
    order: Order,
    *,
    now: datetime | None = None,
) -> Subscription:
    """支付成功后立即升级，并从现有到期日或当前时间延长一个周期。"""
    if order.billing_cycle not in PAID_CYCLES:
        raise ValueError("订单计费周期无效")

    now = as_utc(now or utcnow())
    subscription = await ensure_user_subscription(db, user, for_update=True)
    if subscription.latest_order_id == order.id and subscription.status == "active":
        return subscription

    period_start, period_end = purchased_period(
        current_membership_id=subscription.membership_id,
        target_membership_id=order.membership_id,
        current_start=subscription.current_period_start,
        current_end=subscription.current_period_end,
        current_status=subscription.status,
        billing_cycle=order.billing_cycle,
        now=now,
    )

    subscription.membership_id = order.membership_id
    subscription.status = "active"
    subscription.billing_cycle = order.billing_cycle
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.auto_renew = False
    subscription.cancel_at_period_end = False
    subscription.provider = "alipay"
    subscription.provider_subscription_id = None
    subscription.latest_order_id = order.id
    subscription.updated_at = now

    user.membership_id = order.membership_id
    target_membership = (
        await db.execute(select(Membership).where(Membership.id == order.membership_id))
    ).scalar_one()
    user.membership = target_membership
    user.subscription = subscription
    await db.flush()
    return subscription


async def reconcile_user_subscription(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> Subscription:
    """请求期间兜底检查到期状态，避免等待定时任务后才降级。"""
    now = as_utc(now or utcnow())
    subscription = await ensure_user_subscription(db, user)
    period_end = (
        as_utc(subscription.current_period_end)
        if subscription.current_period_end is not None
        else None
    )
    if subscription.status in {"active", "internal"} and period_end and period_end <= now:
        free_membership = (
            await db.execute(select(Membership).where(Membership.id == FREE_MEMBERSHIP_ID))
        ).scalar_one()
        subscription.status = "expired"
        subscription.auto_renew = False
        subscription.cancel_at_period_end = False
        subscription.updated_at = now
        user.membership_id = FREE_MEMBERSHIP_ID
        user.membership = free_membership
        await db.flush()
    user.subscription = subscription
    return subscription


async def expire_due_subscriptions(db: AsyncSession, *, now: datetime | None = None) -> int:
    """批量过期已结束的付费订阅，并将用户降级到 Free。"""
    now = as_utc(now or utcnow())
    # 所有写路径统一按 User -> Subscription 的顺序加锁，避免与支付和额度结算死锁。
    users = (
        await db.execute(
            select(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.status.in_(["active", "internal"]),
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end <= now,
            )
            .with_for_update(of=User, skip_locked=True)
        )
    ).scalars().all()
    if not users:
        return 0

    expired_count = 0
    for user in users:
        subscription = (
            await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .with_for_update()
            )
        ).scalar_one()
        period_end = (
            as_utc(subscription.current_period_end)
            if subscription.current_period_end is not None
            else None
        )
        if subscription.status not in {"active", "internal"} or period_end is None or period_end > now:
            continue
        subscription.status = "expired"
        subscription.auto_renew = False
        subscription.cancel_at_period_end = False
        subscription.updated_at = now
        user.membership_id = FREE_MEMBERSHIP_ID
        expired_count += 1
    await db.flush()
    return expired_count
