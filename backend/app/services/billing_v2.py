"""V-Credits catalog, quote, wallet and hold services.

The service intentionally keeps money in fen and credits as integers.  A job may
reserve credits before execution, then capture or release that reservation
exactly once.
"""

import math
import calendar
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    BillableSku,
    BillingAccount,
    BillingCatalogVersion,
    BillingPlanVersion,
    BillingQuote,
    BillingQuoteLine,
    CreditHold,
    CreditHoldItem,
    CreditLedger,
    CreditLot,
    CreditPackage,
    RateCardEntry,
)
from app.models.user import User
from app.models.subscription import Subscription


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _add_months(value: datetime, months: int) -> datetime:
    value = as_utc(value)
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def subscription_order_period_start(
    current_period_start: datetime,
    current_period_end: datetime,
    billing_cycle: str,
) -> datetime:
    """Return the entitlement start owned by the subscription's latest order.

    ``Subscription.current_period_start`` remains the original subscription
    anchor when the same plan is renewed, while ``latest_order_id`` advances.
    Deriving the latest order's window from the current end prevents a renewal
    order from granting all historical monthly credits again.
    """
    months = {"monthly": 1, "yearly": 12}.get(billing_cycle)
    if months is None:
        raise ValueError("订阅计费周期必须是 monthly 或 yearly")
    start = as_utc(current_period_start)
    latest_window_start = _add_months(as_utc(current_period_end), -months)
    return max(start, latest_window_start)


def _account_total(account: BillingAccount) -> int:
    """Economic wallet balance, including credits currently held by jobs."""
    return max(0, int(account.cached_available_credits + account.cached_reserved_credits))


def calculate_topup_credits(
    base_credits: int,
    package_bonus_bps: int = 0,
    membership_bonus_bps: int = 0,
) -> int:
    """按商业目录计算充值到账积分。

    Excel 06 的规则是先叠加“积分包赠送”，再对包赠送后的数量叠加会员
    加成，即 ``base * (1 + package) * (1 + membership)``。每一层都按整
    数积分向下取整，避免给出不可结算的小数积分。
    """
    base = int(base_credits)
    if base <= 0:
        raise ValueError("基础积分必须大于 0")
    package_bonus = max(0, int(package_bonus_bps))
    membership_bonus = max(0, int(membership_bonus_bps))
    after_package = base + (base * package_bonus // 10000)
    return after_package + (after_package * membership_bonus // 10000)


async def active_catalog(db: AsyncSession, *, now: datetime | None = None) -> BillingCatalogVersion | None:
    now = as_utc(now or utcnow())
    result = await db.execute(
        select(BillingCatalogVersion)
        .where(
            BillingCatalogVersion.status == "published",
            or_(BillingCatalogVersion.effective_at.is_(None), BillingCatalogVersion.effective_at <= now),
        )
        .order_by(BillingCatalogVersion.effective_at.desc().nullslast(), BillingCatalogVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def active_plan_for_user(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> BillingPlanVersion | None:
    """Resolve the plan in the currently published catalog for a user.

    Subscription membership is the compatibility bridge for existing users;
    the published catalog remains the source of truth for runtime entitlements.
    """
    catalog = await active_catalog(db, now=now)
    if catalog is None:
        return None
    membership_id = user.membership_id
    subscription = (
        await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    ).scalar_one_or_none()
    if subscription and subscription.status in {"active", "internal"}:
        membership_id = subscription.membership_id
    if not membership_id:
        membership_id = "membership-free"
    return (
        await db.execute(
            select(BillingPlanVersion).where(
                BillingPlanVersion.catalog_version_id == catalog.id,
                BillingPlanVersion.membership_id == membership_id,
            )
        )
    ).scalar_one_or_none()


_VIDEO_RESOLUTION_RANK = {"480p": 1, "720p": 2, "1080p": 3, "2k": 4, "4k": 5}
_IMAGE_RESOLUTION_RANK = {"1k": 1, "2k": 2, "4k": 3}


def validate_plan_generation_entitlements(
    plan: BillingPlanVersion | None,
    *,
    operation: str,
    resolution: str | None = None,
    batch: bool = False,
) -> None:
    """Raise ValueError when a request exceeds the published plan limits."""
    if plan is None:
        return
    if batch and not plan.batch_access:
        raise ValueError("当前套餐不支持批量生成")
    if operation == "video" and resolution:
        requested = _VIDEO_RESOLUTION_RANK.get(str(resolution).strip().lower())
        allowed = _VIDEO_RESOLUTION_RANK.get(str(plan.max_video_resolution).strip().lower())
        if requested and allowed and requested > allowed:
            raise ValueError(f"当前套餐最高支持 {plan.max_video_resolution} 视频分辨率")
    if operation == "image" and resolution:
        requested = _IMAGE_RESOLUTION_RANK.get(str(resolution).strip().lower())
        allowed = _IMAGE_RESOLUTION_RANK.get(str(plan.max_image_resolution).strip().lower())
        if requested and allowed and requested > allowed:
            raise ValueError(f"当前套餐最高支持 {plan.max_image_resolution} 图片分辨率")


async def ensure_billing_account(
    db: AsyncSession,
    owner_type: str,
    owner_id: str,
    *,
    for_update: bool = False,
) -> BillingAccount:
    query = select(BillingAccount).where(
        BillingAccount.owner_type == owner_type,
        BillingAccount.owner_id == owner_id,
    )
    if for_update:
        query = query.with_for_update()
    account = (await db.execute(query)).scalar_one_or_none()
    if account is not None:
        return account
    account = BillingAccount(owner_type=owner_type, owner_id=owner_id)
    # “首次注册/首次请求钱包”可能在并发请求中同时到达。使用保存点承
    # 接唯一键冲突，再读取已经由另一事务创建的账户，避免把正常竞态暴
    # 露成 500。
    try:
        async with db.begin_nested():
            db.add(account)
            await db.flush()
    except IntegrityError:
        account = (await db.execute(query)).scalar_one_or_none()
        if account is None:
            raise
    return account


async def ensure_user_billing_account(
    db: AsyncSession,
    user: User,
    *,
    for_update: bool = False,
) -> BillingAccount:
    return await ensure_billing_account(db, "user", user.id, for_update=for_update)


async def grant_signup_credits_for_user(
    db: AsyncSession,
    user: User,
    *,
    reason: str = "注册赠送积分",
) -> CreditLot | None:
    """按当前已发布目录发放一次注册积分。

    该函数只应在“新用户创建”路径调用。幂等键仍由流水唯一约束兜底，
    因此重复回调或事务重试不会重复增加余额。
    """
    catalog = await active_catalog(db)
    if catalog is None:
        return None
    plan = (
        await db.execute(
            select(BillingPlanVersion)
            .where(
                BillingPlanVersion.catalog_version_id == catalog.id,
                BillingPlanVersion.plan_code == "free",
            )
        )
    ).scalar_one_or_none()
    amount = int(plan.signup_credits) if plan else 0
    if amount <= 0:
        return None
    account = await ensure_user_billing_account(db, user, for_update=True)
    return await grant_credits(
        db,
        account,
        amount,
        source_type="signup_bonus",
        source_id=user.id,
        catalog_version_id=catalog.id,
        reason=reason,
        idempotency_key=f"signup:{user.id}:catalog:{catalog.id}",
        metadata={"plan_code": "free"},
    )


async def grant_subscription_credits(
    db: AsyncSession,
    user: User,
    *,
    membership_id: str,
    order_id: str,
    period_end: datetime | None,
    period_start: datetime | None = None,
    catalog_version_id: str | None = None,
    now: datetime | None = None,
) -> CreditLot | None:
    """支付成功后发放该周期积分；按订单幂等，支持重复支付回调。"""
    catalog = (
        await db.get(BillingCatalogVersion, catalog_version_id)
        if catalog_version_id
        else await active_catalog(db)
    )
    if catalog is None:
        return None
    plan = (
        await db.execute(
            select(BillingPlanVersion).where(
                BillingPlanVersion.catalog_version_id == catalog.id,
                BillingPlanVersion.membership_id == membership_id,
            )
        )
    ).scalar_one_or_none()
    if plan is None or int(plan.monthly_credits) <= 0:
        return None
    # 年付也按月发放。未显式传入周期起点时，兼容旧调用方：用周期结束
    # 前一个月推导本次周期；没有结束时间则从当前时间开始。
    now = as_utc(now or utcnow())
    cycle_start = as_utc(period_start) if period_start else (
        _add_months(as_utc(period_end), -1) if period_end else utcnow()
    )
    # 提前续费只延长订阅，不提前释放未来月份积分。到达周期起点后由定时
    # 任务按相同幂等键补发。
    if cycle_start > now:
        return None
    cycle_end = _add_months(cycle_start, 1)
    # 月度积分最多保留最近 N 个周期；N=3 时，本周期积分在发放日起
    # 三个月后到期（当前周期 + 两个历史周期），不能再额外多算一个月。
    rollover_cycles = max(1, int(plan.rollover_cycles) or 1)
    expires = _add_months(cycle_start, rollover_cycles)
    account = await ensure_user_billing_account(db, user, for_update=True)
    return await grant_credits(
        db,
        account,
        int(plan.monthly_credits),
        source_type="subscription_monthly",
        source_id=order_id,
        expires_at=expires,
        catalog_version_id=catalog.id,
        reason=f"{plan.display_name} 订阅周期积分",
        idempotency_key=f"subscription:{order_id}:cycle:{cycle_start.isoformat()}:catalog:{catalog.id}",
        metadata={
            "plan_code": plan.plan_code,
            "period_start": cycle_start.isoformat(),
            "period_end": period_end.isoformat() if period_end else cycle_end.isoformat(),
        },
    )


async def grant_due_subscription_credits(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = 200,
) -> int:
    """补发已经进入当前周期但尚未到账的月度积分。

    年付订阅也走这里，因此不会一次性把 12 个月积分全部发出。流水的
    周期幂等键允许 Beat 重复执行，且历史订单目录快照优先于当前目录。
    """
    now = as_utc(now or utcnow())
    from app.models.order import Order
    from app.models.subscription import Subscription

    issued = 0
    page_size = max(1, min(batch_size, 1000))
    after_user_id: str | None = None
    while True:
        query = (
            select(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.status == "active",
                Subscription.billing_cycle.in_(("monthly", "yearly")),
                Subscription.current_period_start <= now,
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end > now,
            )
            .order_by(User.id)
            .with_for_update(of=User, skip_locked=True)
            .limit(page_size)
        )
        if after_user_id is not None:
            query = query.where(User.id > after_user_id)
        users = (await db.execute(query)).scalars().all()
        if not users:
            break
        after_user_id = users[-1].id
        for user in users:
            subscription = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user.id).with_for_update()
                )
            ).scalar_one_or_none()
            if not subscription or not subscription.latest_order_id or not subscription.current_period_end:
                continue
            order = await db.get(Order, subscription.latest_order_id)
            if not order or order.status != "paid":
                continue
            period_end = as_utc(subscription.current_period_end)
            cycle_anchor = subscription_order_period_start(
                subscription.current_period_start,
                period_end,
                order.billing_cycle,
            )
            cycle_index = 0
            while True:
                cycle_start = _add_months(cycle_anchor, cycle_index)
                if cycle_start > now or cycle_start >= period_end:
                    break
                lot = await grant_subscription_credits(
                    db,
                    user,
                    membership_id=subscription.membership_id,
                    order_id=order.id,
                    period_start=cycle_start,
                    period_end=min(_add_months(cycle_anchor, cycle_index + 1), period_end),
                    catalog_version_id=order.catalog_version_id,
                    now=now,
                )
                issued += 1 if lot is not None else 0
                cycle_index += 1
    return issued


async def _expire_lots(db: AsyncSession, account: BillingAccount, *, now: datetime) -> int:
    lots = (
        await db.execute(
            select(CreditLot)
            .where(
                CreditLot.billing_account_id == account.id,
                CreditLot.remaining_amount > 0,
                CreditLot.expires_at.is_not(None),
                CreditLot.expires_at <= now,
            )
            .with_for_update()
        )
    ).scalars().all()
    expired = 0
    for lot in lots:
        amount = int(lot.remaining_amount)
        if amount <= 0:
            continue
        lot.remaining_amount = 0
        account.cached_available_credits = max(0, account.cached_available_credits - amount)
        db.add(
            CreditLedger(
                billing_account_id=account.id,
                credit_lot_id=lot.id,
                entry_type="expire",
                amount=-amount,
                balance_after=_account_total(account),
                reason="积分批次到期",
                idempotency_key=f"expire:{lot.id}",
            )
        )
        expired += amount
    if expired:
        await db.flush()
    return expired


async def grant_credits(
    db: AsyncSession,
    account: BillingAccount,
    amount: int,
    *,
    source_type: str,
    source_id: str | None = None,
    expires_at: datetime | None = None,
    catalog_version_id: str | None = None,
    reason: str = "",
    idempotency_key: str,
    metadata: dict | None = None,
) -> CreditLot:
    if amount <= 0:
        raise ValueError("积分发放数量必须大于 0")
    existing = (
        await db.execute(
            select(CreditLedger).where(
                CreditLedger.billing_account_id == account.id,
                CreditLedger.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.credit_lot_id:
        lot = await db.get(CreditLot, existing.credit_lot_id)
        if lot:
            return lot
    account = await ensure_billing_account(db, account.owner_type, account.owner_id, for_update=True)
    # 必须在账户行锁之后再次检查幂等键。第一次查询可能发生在另一
    # 个并发事务提交前，否则两个请求都会创建批次并在唯一键处失败。
    existing = (
        await db.execute(
            select(CreditLedger).where(
                CreditLedger.billing_account_id == account.id,
                CreditLedger.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.credit_lot_id:
        lot = await db.get(CreditLot, existing.credit_lot_id)
        if lot:
            return lot
    expires_at = as_utc(expires_at) if expires_at else None
    lot = CreditLot(
        billing_account_id=account.id,
        source_type=source_type,
        source_id=source_id,
        original_amount=amount,
        remaining_amount=amount,
        granted_at=utcnow(),
        expires_at=expires_at,
        catalog_version_id=catalog_version_id,
        metadata_json=metadata or {},
    )
    db.add(lot)
    await db.flush()
    account.cached_available_credits += amount
    db.add(
        CreditLedger(
            billing_account_id=account.id,
            credit_lot_id=lot.id,
            entry_type="grant",
            amount=amount,
            balance_after=_account_total(account),
            order_id=source_id if source_type in {"topup_purchase", "subscription_monthly"} else None,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    )
    await db.flush()
    return lot


async def wallet_balance(db: AsyncSession, account: BillingAccount, *, now: datetime | None = None) -> dict[str, int]:
    now = as_utc(now or utcnow())
    account = await ensure_billing_account(db, account.owner_type, account.owner_id, for_update=True)
    await _expire_lots(db, account, now=now)
    return {
        "available_credits": max(0, int(account.cached_available_credits)),
        "reserved_credits": max(0, int(account.cached_reserved_credits)),
        "total_credits": max(0, int(account.cached_available_credits + account.cached_reserved_credits)),
    }


async def reserve_credits(
    db: AsyncSession,
    account: BillingAccount,
    amount: int,
    *,
    idempotency_key: str,
    job_id: str | None = None,
    quote_id: str | None = None,
    expires_at: datetime | None = None,
    reason: str = "任务积分预占",
) -> CreditHold:
    if amount <= 0:
        raise ValueError("积分预占数量必须大于 0")
    existing = (
        await db.execute(select(CreditHold).where(CreditHold.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.billing_account_id != account.id:
            raise ValueError("积分预占幂等键已属于其他钱包")
        return existing
    now = utcnow()
    account = await ensure_billing_account(db, account.owner_type, account.owner_id, for_update=True)
    existing = (
        await db.execute(select(CreditHold).where(CreditHold.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.billing_account_id != account.id:
            raise ValueError("积分预占幂等键已属于其他钱包")
        return existing
    await _expire_lots(db, account, now=now)
    if quote_id:
        quote = (
            await db.execute(
                select(BillingQuote)
                .where(BillingQuote.id == quote_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if quote is None or quote.billing_account_id != account.id:
            raise ValueError("报价不存在或不属于当前钱包")
        if quote.status != "issued":
            raise ValueError("报价已使用或已失效")
        if as_utc(quote.expires_at) <= now:
            quote.status = "expired"
            raise ValueError("报价已过期，请重新报价")
        if int(quote.total_credits) != int(amount):
            raise ValueError("报价金额与预占积分不一致")
    if account.cached_available_credits < amount:
        raise ValueError("V-Credits 余额不足")

    lots = (
        await db.execute(
            select(CreditLot)
            .where(CreditLot.billing_account_id == account.id, CreditLot.remaining_amount > 0)
            .order_by(CreditLot.expires_at.is_(None), CreditLot.expires_at, CreditLot.granted_at, CreditLot.id)
            .with_for_update()
        )
    ).scalars().all()
    remaining = amount
    allocations: list[tuple[CreditLot, int]] = []
    for lot in lots:
        take = min(remaining, int(lot.remaining_amount))
        if take <= 0:
            continue
        lot.remaining_amount -= take
        allocations.append((lot, take))
        remaining -= take
        if remaining == 0:
            break
    if remaining:
        raise ValueError("V-Credits 余额与批次不一致，请刷新后重试")

    hold = CreditHold(
        billing_account_id=account.id,
        quote_id=quote_id,
        job_id=job_id,
        amount=amount,
        status="active",
        idempotency_key=idempotency_key,
        expires_at=as_utc(expires_at) if expires_at else None,
    )
    db.add(hold)
    await db.flush()
    for lot, allocated in allocations:
        db.add(CreditHoldItem(hold_id=hold.id, credit_lot_id=lot.id, amount=allocated))
    account.cached_available_credits -= amount
    account.cached_reserved_credits += amount
    if quote_id:
        quote.status = "consumed"
        quote.consumed_at = now
    db.add(
        CreditLedger(
            billing_account_id=account.id,
            entry_type="reserve",
            amount=0,
            balance_after=_account_total(account),
            quote_id=quote_id,
            job_id=job_id,
            reason=reason,
            idempotency_key=f"reserve:{idempotency_key}",
        )
    )
    await db.flush()
    return hold


async def capture_hold(db: AsyncSession, hold_id: str, *, reason: str = "任务成功结算") -> bool:
    hold = (await db.execute(select(CreditHold).where(CreditHold.id == hold_id).with_for_update())).scalar_one_or_none()
    if hold is None:
        return False
    if hold.status == "captured":
        return False
    if hold.status != "active":
        return False
    account = (
        await db.execute(
            select(BillingAccount)
            .where(BillingAccount.id == hold.billing_account_id)
            .with_for_update()
        )
    ).scalar_one()
    account.cached_reserved_credits = max(0, account.cached_reserved_credits - hold.amount)
    hold.status = "captured"
    hold.updated_at = utcnow()
    db.add(
        CreditLedger(
            billing_account_id=account.id,
            entry_type="capture",
            amount=-hold.amount,
            balance_after=_account_total(account),
            quote_id=hold.quote_id,
            job_id=hold.job_id,
            reason=reason,
            idempotency_key=f"capture:{hold.id}",
        )
    )
    await db.flush()
    return True


async def release_hold(db: AsyncSession, hold_id: str, *, reason: str = "任务失败释放") -> bool:
    hold = (await db.execute(select(CreditHold).where(CreditHold.id == hold_id).with_for_update())).scalar_one_or_none()
    if hold is None or hold.status != "active":
        return False
    account = (await db.execute(select(BillingAccount).where(BillingAccount.id == hold.billing_account_id).with_for_update())).scalar_one()
    items = (await db.execute(select(CreditHoldItem).where(CreditHoldItem.hold_id == hold.id).with_for_update())).scalars().all()
    for item in items:
        lot = (await db.execute(select(CreditLot).where(CreditLot.id == item.credit_lot_id).with_for_update())).scalar_one()
        lot.remaining_amount += item.amount
    account.cached_available_credits += hold.amount
    account.cached_reserved_credits = max(0, account.cached_reserved_credits - hold.amount)
    hold.status = "released"
    hold.updated_at = utcnow()
    db.add(
        CreditLedger(
            billing_account_id=account.id,
            entry_type="release",
            amount=0,
            balance_after=_account_total(account),
            quote_id=hold.quote_id,
            job_id=hold.job_id,
            reason=reason,
            idempotency_key=f"release:{hold.id}",
        )
    )
    await db.flush()
    return True


async def create_usage_quote(
    db: AsyncSession,
    account: BillingAccount,
    lines: list[dict],
    *,
    request_snapshot: dict,
    ttl_seconds: int = 300,
) -> BillingQuote:
    catalog = await active_catalog(db)
    if catalog is None:
        raise ValueError("当前没有已发布的计费目录")
    if not lines:
        raise ValueError("至少需要一个计费项目")
    total = 0
    normalized_lines: list[dict] = []
    for raw in lines:
        sku_name = str(raw.get("sku") or "").strip()
        raw_quantity = float(raw.get("quantity") or 0)
        if not math.isfinite(raw_quantity):
            raise ValueError("计费数量必须是有限数字")
        quantity = int(math.ceil(raw_quantity))
        if not sku_name or quantity <= 0:
            raise ValueError("计费项目和数量无效")
        row = (
            await db.execute(
                select(BillableSku, RateCardEntry)
                .join(RateCardEntry, RateCardEntry.sku_id == BillableSku.id)
                .where(
                    BillableSku.catalog_version_id == catalog.id,
                    BillableSku.sku == sku_name,
                    BillableSku.active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            raise ValueError(f"计费 SKU 不存在或已下架：{sku_name}")
        sku, rate = row
        quantity = max(quantity, int(sku.minimum_quantity or 1))
        if account.owner_type == "user":
            allowed_plan_codes = set(rate.allowed_plan_codes or [])
            if not allowed_plan_codes:
                raise ValueError(f"计费 SKU 尚未配置可用套餐：{sku_name}")
            user_membership_id = (
                await db.execute(
                    select(User.membership_id).where(User.id == account.owner_id)
                )
            ).scalar_one_or_none()
            plan_code = (
                await db.execute(
                    select(BillingPlanVersion.plan_code)
                    .where(
                        BillingPlanVersion.catalog_version_id == catalog.id,
                        BillingPlanVersion.membership_id == user_membership_id,
                    )
                )
            ).scalar_one_or_none() or "free"
            if plan_code not in allowed_plan_codes:
                raise ValueError(f"当前会员无法使用该计费 SKU：{sku_name}")
        credits = max(int(rate.minimum_credits), int(rate.credits_per_unit) * quantity)
        total += credits
        normalized_lines.append({
            "sku_id": sku.id,
            "sku": sku.sku,
            "unit": sku.unit,
            "quantity": quantity,
            "unit_credits": int(rate.credits_per_unit),
            "credits": credits,
            "metadata": raw.get("metadata") or {},
        })

    quote = BillingQuote(
        billing_account_id=account.id,
        catalog_version_id=catalog.id,
        total_credits=total,
        request_snapshot=request_snapshot,
        expires_at=utcnow() + timedelta(seconds=max(30, ttl_seconds)),
        status="issued",
    )
    db.add(quote)
    await db.flush()
    for line in normalized_lines:
        db.add(BillingQuoteLine(quote_id=quote.id, **line))
    await db.flush()
    return quote


async def quote_lines(db: AsyncSession, quote_id: str) -> list[BillingQuoteLine]:
    return (
        await db.execute(select(BillingQuoteLine).where(BillingQuoteLine.quote_id == quote_id).order_by(BillingQuoteLine.id))
    ).scalars().all()
