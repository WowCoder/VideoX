"""V-Credits 商业目录与钱包 API。

该路由只读/报价，不直接处理支付。支付订单成功后的积分发放应调用
``grant_credits``，生成任务则使用报价 + hold 的预占/结算生命周期。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.billing import (
    BillableSku,
    BillingPlanVersion,
    CreditPackage,
    CreditLedger,
    CreditLot,
    RateCardEntry,
)
from app.models.user import User
from app.services.billing_v2 import (
    active_catalog,
    create_usage_quote,
    ensure_user_billing_account,
    quote_lines,
    wallet_balance,
)


router = APIRouter()


class CatalogPlanOut(BaseModel):
    plan_code: str
    membership_id: str | None = None
    display_name: str
    rank: int
    monthly_price_fen: int
    annual_price_fen: int | None
    monthly_credits: int
    signup_credits: int
    rollover_cycles: int
    recharge_bonus_bps: int
    generation_concurrency: int
    storage_bytes: int
    seat_limit: int
    queue_priority: int
    model_access_level: str
    max_video_resolution: str
    max_image_resolution: str
    watermark_required: bool
    commercial_use: bool
    api_access: bool
    batch_access: bool
    rollover_policy: str
    metadata: dict = Field(default_factory=dict)


class CatalogPackageOut(BaseModel):
    package_code: str
    display_name: str
    price_fen: int
    base_credits: int
    package_bonus_bps: int
    sort_order: int
    active: bool
    metadata: dict = Field(default_factory=dict)


class CatalogSkuOut(BaseModel):
    sku: str
    display_name: str
    category: str
    unit: str
    minimum_quantity: int
    rounding_mode: str
    access_level: str
    credits_per_unit: int
    minimum_credits: int
    allowed_plan_codes: list[str] = Field(default_factory=list)
    included_in_pass: bool
    metadata: dict = Field(default_factory=dict)


class CatalogOut(BaseModel):
    id: str
    version_key: str
    status: str
    effective_at: datetime | None
    published_at: datetime | None
    plans: list[CatalogPlanOut]
    credit_packages: list[CatalogPackageOut]
    skus: list[CatalogSkuOut]


class CreditLotOut(BaseModel):
    id: str
    source_type: str
    source_id: str | None
    original_amount: int
    remaining_amount: int
    granted_at: datetime
    expires_at: datetime | None


class WalletOut(BaseModel):
    account_id: str
    owner_type: str
    owner_id: str
    available_credits: int
    reserved_credits: int
    total_credits: int
    lots: list[CreditLotOut]


class LedgerOut(BaseModel):
    id: str
    entry_type: str
    amount: int
    balance_after: int
    reason: str
    order_id: str | None
    quote_id: str | None
    job_id: str | None
    credit_lot_id: str | None
    idempotency_key: str
    created_at: datetime


class QuoteLineRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=120)
    quantity: float = Field(..., gt=0)
    metadata: dict = Field(default_factory=dict)


class QuoteRequest(BaseModel):
    lines: list[QuoteLineRequest] = Field(..., min_length=1, max_length=100)
    request_snapshot: dict = Field(default_factory=dict)
    ttl_seconds: int = Field(300, ge=30, le=3600)


class QuoteLineOut(BaseModel):
    sku: str
    unit: str
    quantity: int
    unit_credits: int
    credits: int
    metadata: dict = Field(default_factory=dict)


class QuoteOut(BaseModel):
    id: str
    catalog_version_id: str
    total_credits: int
    currency: str
    request_snapshot: dict
    expires_at: datetime
    status: str
    lines: list[QuoteLineOut]


@router.get("/catalog", response_model=CatalogOut)
async def get_catalog(db: AsyncSession = Depends(get_db)):
    """返回官网、客户端和后台共同使用的已发布商业目录。"""
    catalog = await active_catalog(db)
    if catalog is None:
        raise HTTPException(status_code=503, detail="当前没有已发布的计费目录")

    plans = (
        await db.execute(
            select(BillingPlanVersion)
            .where(BillingPlanVersion.catalog_version_id == catalog.id)
            .order_by(BillingPlanVersion.rank, BillingPlanVersion.plan_code)
        )
    ).scalars().all()
    packages = (
        await db.execute(
            select(CreditPackage)
            .where(CreditPackage.catalog_version_id == catalog.id, CreditPackage.active.is_(True))
            .order_by(CreditPackage.sort_order, CreditPackage.package_code)
        )
    ).scalars().all()
    skus = (
        await db.execute(
            select(BillableSku)
            .where(BillableSku.catalog_version_id == catalog.id, BillableSku.active.is_(True))
            .order_by(BillableSku.category, BillableSku.sku)
        )
    ).scalars().all()
    rates = (
        await db.execute(
            select(RateCardEntry).where(RateCardEntry.catalog_version_id == catalog.id)
        )
    ).scalars().all()
    rates_by_sku = {rate.sku_id: rate for rate in rates}
    return CatalogOut(
        id=catalog.id,
        version_key=catalog.version_key,
        status=catalog.status,
        effective_at=catalog.effective_at,
        published_at=catalog.published_at,
        plans=[
            CatalogPlanOut(
                plan_code=plan.plan_code,
                membership_id=plan.membership_id,
                display_name=plan.display_name,
                rank=plan.rank,
                monthly_price_fen=plan.monthly_price_fen,
                annual_price_fen=plan.annual_price_fen,
                monthly_credits=plan.monthly_credits,
                signup_credits=plan.signup_credits,
                rollover_cycles=plan.rollover_cycles,
                recharge_bonus_bps=plan.recharge_bonus_bps,
                generation_concurrency=plan.generation_concurrency,
                storage_bytes=plan.storage_bytes,
                seat_limit=plan.seat_limit,
                queue_priority=plan.queue_priority,
                model_access_level=plan.model_access_level,
                max_video_resolution=plan.max_video_resolution,
                max_image_resolution=plan.max_image_resolution,
                watermark_required=plan.watermark_required,
                commercial_use=plan.commercial_use,
                api_access=plan.api_access,
                batch_access=plan.batch_access,
                rollover_policy=plan.rollover_policy,
                metadata=plan.metadata_json or {},
            )
            for plan in plans
        ],
        credit_packages=[
            CatalogPackageOut(
                package_code=package.package_code,
                display_name=package.display_name,
                price_fen=package.price_fen,
                base_credits=package.base_credits,
                package_bonus_bps=package.package_bonus_bps,
                sort_order=package.sort_order,
                active=package.active,
                metadata=package.metadata_json or {},
            )
            for package in packages
            if package.active
        ],
        skus=[
            CatalogSkuOut(
                sku=sku.sku,
                display_name=sku.display_name,
                category=sku.category,
                unit=sku.unit,
                minimum_quantity=sku.minimum_quantity,
                rounding_mode=sku.rounding_mode,
                access_level=sku.access_level,
                credits_per_unit=int(rates_by_sku[sku.id].credits_per_unit),
                minimum_credits=int(rates_by_sku[sku.id].minimum_credits),
                allowed_plan_codes=list(rates_by_sku[sku.id].allowed_plan_codes or []),
                included_in_pass=bool(rates_by_sku[sku.id].included_in_pass),
                metadata={**(sku.metadata_json or {}), **(rates_by_sku[sku.id].metadata_json or {})},
            )
            for sku in skus
            if sku.id in rates_by_sku
        ],
    )


@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await ensure_user_billing_account(db, user, for_update=True)
    balance = await wallet_balance(db, account)
    lots = (
        await db.execute(
            select(CreditLot)
            .where(CreditLot.billing_account_id == account.id, CreditLot.remaining_amount > 0)
            .order_by(CreditLot.expires_at.is_(None), CreditLot.expires_at, CreditLot.granted_at)
        )
    ).scalars().all()
    return WalletOut(
        account_id=account.id,
        owner_type=account.owner_type,
        owner_id=account.owner_id,
        **balance,
        lots=[CreditLotOut.model_validate(lot, from_attributes=True) for lot in lots],
    )


@router.get("/ledger", response_model=list[LedgerOut])
async def get_ledger(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await ensure_user_billing_account(db, user)
    rows = (
        await db.execute(
            select(CreditLedger)
            .where(CreditLedger.billing_account_id == account.id)
            .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return [LedgerOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/quotes", response_model=QuoteOut)
async def create_quote(
    request: QuoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await ensure_user_billing_account(db, user)
    try:
        quote = await create_usage_quote(
            db,
            account,
            [line.model_dump() for line in request.lines],
            request_snapshot={
                **request.request_snapshot,
                "user_id": user.id,
            },
            ttl_seconds=request.ttl_seconds,
        )
        lines = await quote_lines(db, quote.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QuoteOut(
        id=quote.id,
        catalog_version_id=quote.catalog_version_id,
        total_credits=quote.total_credits,
        currency=quote.currency,
        request_snapshot=quote.request_snapshot or {},
        expires_at=quote.expires_at,
        status=quote.status,
        lines=[
            QuoteLineOut(
                sku=line.sku,
                unit=line.unit,
                quantity=line.quantity,
                unit_credits=line.unit_credits,
                credits=line.credits,
                metadata=line.metadata_json or {},
            )
            for line in lines
        ],
    )
