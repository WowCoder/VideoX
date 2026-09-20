"""运营后台订单、订阅一致性和发票查询。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.orm.attributes import NO_VALUE
from sqlalchemy import inspect as sa_inspect

from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.audit import validate_idempotent_target, write_admin_audit
from app.admin.redaction import mask_email
from app.database import get_db
from app.models.invoice import Invoice
from app.models.admin import AdminAuditLog
from app.models.billing import (
    BillableSku,
    BillingCatalogVersion,
    BillingPlanVersion,
    CreditPackage,
    PassProduct,
    RateCardEntry,
)
from app.models.order import Order
from app.models.subscription import Subscription, SubscriptionEvent
from app.models.user import User
from app.config import get_settings
from app.services.quotas import synchronize_user_usage
from app.services.subscriptions import activate_paid_subscription
from app.services.billing_v2 import grant_subscription_credits


router = APIRouter()


class BillingReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class InvoiceRejectRequest(BillingReasonRequest):
    pass


class InvoiceIssueRequest(BillingReasonRequest):
    invoice_number: str = Field(..., min_length=3, max_length=100)
    document_path: str | None = Field(None, max_length=1000)


class CatalogDraftRequest(BaseModel):
    version_key: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    source_catalog_id: str | None = None
    notes: str = Field("", max_length=2000)


class PlanPatchRequest(BaseModel):
    monthly_price_fen: int | None = Field(None, ge=0)
    annual_price_fen: int | None = Field(None, ge=0)
    monthly_credits: int | None = Field(None, ge=0)
    signup_credits: int | None = Field(None, ge=0)
    rollover_cycles: int | None = Field(None, ge=0, le=120)
    recharge_bonus_bps: int | None = Field(None, ge=0, le=10000)
    generation_concurrency: int | None = Field(None, ge=1)
    storage_bytes: int | None = Field(None, ge=0)
    seat_limit: int | None = Field(None, ge=1)
    queue_priority: int | None = Field(None, ge=0, le=100)
    model_access_level: str | None = Field(None, min_length=2, max_length=50)
    max_video_resolution: str | None = Field(None, min_length=2, max_length=20)
    max_image_resolution: str | None = Field(None, min_length=2, max_length=20)
    watermark_required: bool | None = None
    commercial_use: bool | None = None
    api_access: bool | None = None
    batch_access: bool | None = None
    notes: str | None = Field(None, max_length=2000)


class RatePatchRequest(BaseModel):
    credits_per_unit: int | None = Field(None, ge=1)
    minimum_credits: int | None = Field(None, ge=0)
    allowed_plan_codes: list[str] | None = None
    included_in_pass: bool | None = None
    active: bool | None = None


class PackagePatchRequest(BaseModel):
    price_fen: int | None = Field(None, ge=1)
    base_credits: int | None = Field(None, ge=1)
    package_bonus_bps: int | None = Field(None, ge=0, le=10000)
    sort_order: int | None = Field(None, ge=0)
    active: bool | None = None


def _subscription_snapshot(subscription: Subscription | None) -> dict:
    if subscription is None:
        return {}
    return {
        "membership_id": subscription.membership_id,
        "status": subscription.status,
        "billing_cycle": subscription.billing_cycle,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "provider": subscription.provider,
        "latest_order_id": subscription.latest_order_id,
    }


async def _existing_audit(
    db: AsyncSession, admin_id: str, action: str, idempotency_key: str
) -> AdminAuditLog | None:
    return (
        await db.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.admin_user_id == admin_id,
                AdminAuditLog.action == action,
                AdminAuditLog.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


def _mask_tax_number(value: str) -> str:
    return value[:4] + "********" + value[-4:] if len(value) > 8 else "********"


def _catalog_summary(catalog: BillingCatalogVersion) -> dict:
    state = sa_inspect(catalog)

    def relationship_count(name: str) -> int:
        value = state.attrs[name].loaded_value
        return 0 if value is NO_VALUE else len(value)

    return {
        "id": catalog.id,
        "version_key": catalog.version_key,
        "status": catalog.status,
        "effective_at": catalog.effective_at,
        "published_at": catalog.published_at,
        "notes": catalog.notes,
        "created_at": catalog.created_at,
        "updated_at": catalog.updated_at,
        "plan_count": relationship_count("plans"),
        "package_count": relationship_count("credit_packages"),
        "sku_count": relationship_count("skus"),
    }


@router.get("/billing/catalogs")
async def list_catalogs(
    _: AdminPrincipal = Depends(require_admin_permission("pricing.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(BillingCatalogVersion)
            .options(
                selectinload(BillingCatalogVersion.plans),
                selectinload(BillingCatalogVersion.credit_packages),
                selectinload(BillingCatalogVersion.skus),
            )
            .order_by(BillingCatalogVersion.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_catalog_summary(row) for row in rows]}


@router.get("/billing/catalogs/{catalog_id}")
async def get_catalog_detail(
    catalog_id: str,
    _: AdminPrincipal = Depends(require_admin_permission("pricing.read")),
    db: AsyncSession = Depends(get_db),
):
    catalog = (
        await db.execute(
            select(BillingCatalogVersion)
            .where(BillingCatalogVersion.id == catalog_id)
            .options(
                selectinload(BillingCatalogVersion.plans),
                selectinload(BillingCatalogVersion.credit_packages),
                selectinload(BillingCatalogVersion.skus),
                selectinload(BillingCatalogVersion.rate_entries).selectinload(RateCardEntry.sku),
                selectinload(BillingCatalogVersion.passes),
            )
        )
    ).scalar_one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="计费目录不存在")
    return {
        **_catalog_summary(catalog),
        "plans": [
            {
                "id": plan.id,
                "plan_code": plan.plan_code,
                "display_name": plan.display_name,
                "rank": plan.rank,
                "monthly_price_fen": plan.monthly_price_fen,
                "annual_price_fen": plan.annual_price_fen,
                "monthly_credits": plan.monthly_credits,
                "signup_credits": plan.signup_credits,
                "rollover_cycles": plan.rollover_cycles,
                "recharge_bonus_bps": plan.recharge_bonus_bps,
                "generation_concurrency": plan.generation_concurrency,
                "storage_bytes": plan.storage_bytes,
                "seat_limit": plan.seat_limit,
                "queue_priority": plan.queue_priority,
                "model_access_level": plan.model_access_level,
                "max_video_resolution": plan.max_video_resolution,
                "max_image_resolution": plan.max_image_resolution,
                "watermark_required": plan.watermark_required,
                "commercial_use": plan.commercial_use,
                "api_access": plan.api_access,
                "batch_access": plan.batch_access,
                "rollover_policy": plan.rollover_policy,
                "metadata": plan.metadata_json or {},
            }
            for plan in catalog.plans
        ],
        "credit_packages": [
            {
                "id": package.id,
                "package_code": package.package_code,
                "display_name": package.display_name,
                "price_fen": package.price_fen,
                "base_credits": package.base_credits,
                "package_bonus_bps": package.package_bonus_bps,
                "sort_order": package.sort_order,
                "active": package.active,
            }
            for package in catalog.credit_packages
        ],
        "skus": [
            {
                "id": sku.id,
                "sku": sku.sku,
                "display_name": sku.display_name,
                "category": sku.category,
                "unit": sku.unit,
                "active": sku.active,
                "rate": next(
                    (
                        {
                            "credits_per_unit": rate.credits_per_unit,
                            "minimum_credits": rate.minimum_credits,
                            "allowed_plan_codes": rate.allowed_plan_codes or [],
                            "included_in_pass": rate.included_in_pass,
                        }
                        for rate in catalog.rate_entries
                        if rate.sku_id == sku.id
                    ),
                    None,
                ),
            }
            for sku in catalog.skus
        ],
        "passes": [
            {
                "id": item.id,
                "pass_code": item.pass_code,
                "display_name": item.display_name,
                "price_fen": item.price_fen,
                "duration_seconds": item.duration_seconds,
                "model_patterns": item.model_patterns or [],
                "active": item.active,
            }
            for item in catalog.passes
        ],
    }


@router.post("/billing/catalogs", status_code=201)
async def create_catalog_draft(
    payload: CatalogDraftRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("pricing.write")),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(
            select(BillingCatalogVersion).where(BillingCatalogVersion.version_key == payload.version_key)
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="目录版本号已存在")
    source = None
    if payload.source_catalog_id:
        source = (
            await db.execute(
                select(BillingCatalogVersion)
                .where(BillingCatalogVersion.id == payload.source_catalog_id)
                .options(
                    selectinload(BillingCatalogVersion.plans),
                    selectinload(BillingCatalogVersion.credit_packages),
                    selectinload(BillingCatalogVersion.skus),
                    selectinload(BillingCatalogVersion.rate_entries),
                    selectinload(BillingCatalogVersion.passes),
                )
            )
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(status_code=404, detail="源目录不存在")
    catalog = BillingCatalogVersion(
        version_key=payload.version_key,
        status="draft",
        notes=payload.notes.strip(),
        created_by_admin_id=principal.user.id,
    )
    db.add(catalog)
    await db.flush()
    if source:
        sku_map: dict[str, str] = {}
        for source_sku in source.skus:
            copied_sku = BillableSku(
                catalog_version_id=catalog.id,
                sku=source_sku.sku,
                display_name=source_sku.display_name,
                category=source_sku.category,
                unit=source_sku.unit,
                minimum_quantity=source_sku.minimum_quantity,
                rounding_mode=source_sku.rounding_mode,
                access_level=source_sku.access_level,
                active=source_sku.active,
                metadata_json=source_sku.metadata_json or {},
            )
            db.add(copied_sku)
            await db.flush()
            sku_map[source_sku.id] = copied_sku.id
        for plan in source.plans:
            db.add(BillingPlanVersion(
                catalog_version_id=catalog.id,
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
                metadata_json=plan.metadata_json or {},
            ))
        for package in source.credit_packages:
            db.add(CreditPackage(
                catalog_version_id=catalog.id,
                package_code=package.package_code,
                display_name=package.display_name,
                price_fen=package.price_fen,
                base_credits=package.base_credits,
                package_bonus_bps=package.package_bonus_bps,
                sort_order=package.sort_order,
                active=package.active,
                metadata_json=package.metadata_json or {},
            ))
        for rate in source.rate_entries:
            if rate.sku_id in sku_map:
                db.add(RateCardEntry(
                    catalog_version_id=catalog.id,
                    sku_id=sku_map[rate.sku_id],
                    credits_per_unit=rate.credits_per_unit,
                    minimum_credits=rate.minimum_credits,
                    allowed_plan_codes=rate.allowed_plan_codes or [],
                    included_in_pass=rate.included_in_pass,
                    metadata_json=rate.metadata_json or {},
                ))
        for item in source.passes:
            db.add(PassProduct(
                catalog_version_id=catalog.id,
                pass_code=item.pass_code,
                display_name=item.display_name,
                price_fen=item.price_fen,
                duration_seconds=item.duration_seconds,
                model_patterns=item.model_patterns or [],
                resolution_limit=item.resolution_limit,
                concurrency_limit=item.concurrency_limit,
                fair_use_limit=item.fair_use_limit,
                active=item.active,
                metadata_json=item.metadata_json or {},
            ))
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="BILLING_CATALOG_DRAFT_CREATE",
        target_type="billing_catalog",
        target_id=catalog.id,
        reason=payload.notes or "创建计费目录草稿",
        before_data={},
        after_data=_catalog_summary(catalog),
        idempotency_key=f"catalog-create:{catalog.id}",
    )
    return _catalog_summary(catalog)


@router.patch("/billing/catalogs/{catalog_id}/plans/{plan_code}")
async def patch_catalog_plan(
    catalog_id: str,
    plan_code: str,
    payload: PlanPatchRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("pricing.write")),
    db: AsyncSession = Depends(get_db),
):
    catalog = (await db.execute(select(BillingCatalogVersion).where(BillingCatalogVersion.id == catalog_id).with_for_update())).scalar_one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="计费目录不存在")
    if catalog.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿目录允许编辑")
    plan = (await db.execute(select(BillingPlanVersion).where(BillingPlanVersion.catalog_version_id == catalog_id, BillingPlanVersion.plan_code == plan_code).with_for_update())).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="套餐不存在")
    updates = payload.model_dump(exclude_none=True)
    notes = updates.pop("notes", None)
    if notes:
        plan.metadata_json = {**(plan.metadata_json or {}), "admin_notes": notes}
    before = {field: getattr(plan, field) for field in updates}
    for field, value in updates.items():
        setattr(plan, field, value)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="BILLING_PLAN_PATCH",
        target_type="billing_plan",
        target_id=plan.id,
        reason=payload.notes or "调整套餐价格或权益",
        before_data={"catalog_id": catalog_id, "plan_code": plan_code, **before},
        after_data={"catalog_id": catalog_id, "plan_code": plan_code, **updates},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return {"catalog_id": catalog_id, "plan_code": plan_code, "updated": updates}


@router.patch("/billing/catalogs/{catalog_id}/skus/{sku}")
async def patch_catalog_rate(
    catalog_id: str,
    sku: str,
    payload: RatePatchRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("pricing.write")),
    db: AsyncSession = Depends(get_db),
):
    catalog = (await db.execute(select(BillingCatalogVersion).where(BillingCatalogVersion.id == catalog_id).with_for_update())).scalar_one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="计费目录不存在")
    if catalog.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿目录允许编辑")
    row = (await db.execute(select(BillableSku, RateCardEntry).join(RateCardEntry, RateCardEntry.sku_id == BillableSku.id).where(BillableSku.catalog_version_id == catalog_id, BillableSku.sku == sku).with_for_update())).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="SKU 费率不存在")
    sku_row, rate = row
    updates = payload.model_dump(exclude_none=True)
    sku_active = updates.pop("active", None)
    before = {field: getattr(rate, field) for field in updates}
    if sku_active is not None:
        before["active"] = sku_row.active
        sku_row.active = sku_active
    for field, value in updates.items():
        setattr(rate, field, value)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="BILLING_RATE_PATCH",
        target_type="billing_sku",
        target_id=rate.id,
        reason="调整模型或功能点数费率",
        before_data={"catalog_id": catalog_id, "sku": sku, **before},
        after_data={
            "catalog_id": catalog_id,
            "sku": sku,
            **updates,
            **({"active": sku_active} if sku_active is not None else {}),
        },
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return {
        "catalog_id": catalog_id,
        "sku": sku,
        "updated": {**updates, **({"active": sku_active} if sku_active is not None else {})},
    }


@router.patch("/billing/catalogs/{catalog_id}/packages/{package_code}")
async def patch_catalog_package(
    catalog_id: str,
    package_code: str,
    payload: PackagePatchRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("pricing.write")),
    db: AsyncSession = Depends(get_db),
):
    catalog = (
        await db.execute(
            select(BillingCatalogVersion)
            .where(BillingCatalogVersion.id == catalog_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="计费目录不存在")
    if catalog.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿目录允许编辑")
    package = (
        await db.execute(
            select(CreditPackage)
            .where(
                CreditPackage.catalog_version_id == catalog_id,
                CreditPackage.package_code == package_code,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="充值包不存在")
    updates = payload.model_dump(exclude_none=True)
    before = {field: getattr(package, field) for field in updates}
    for field, value in updates.items():
        setattr(package, field, value)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="BILLING_PACKAGE_PATCH",
        target_type="credit_package",
        target_id=package.id,
        reason="调整充值包价格或赠送比例",
        before_data={"catalog_id": catalog_id, "package_code": package_code, **before},
        after_data={"catalog_id": catalog_id, "package_code": package_code, **updates},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return {"catalog_id": catalog_id, "package_code": package_code, "updated": updates}


@router.post("/billing/catalogs/{catalog_id}/publish")
async def publish_catalog(
    catalog_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("pricing.publish")),
    db: AsyncSession = Depends(get_db),
):
    catalog = (
        await db.execute(
            select(BillingCatalogVersion)
            .where(BillingCatalogVersion.id == catalog_id)
            .options(
                selectinload(BillingCatalogVersion.plans),
                selectinload(BillingCatalogVersion.skus),
                selectinload(BillingCatalogVersion.rate_entries),
                selectinload(BillingCatalogVersion.credit_packages),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="计费目录不存在")
    if catalog.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿目录可以发布")
    plan_codes = {plan.plan_code for plan in catalog.plans}
    if "free" not in plan_codes:
        raise HTTPException(status_code=422, detail="目录必须包含 Free 套餐")
    sku_ids = {sku.id for sku in catalog.skus if sku.active}
    rate_sku_ids = {rate.sku_id for rate in catalog.rate_entries}
    if sku_ids - rate_sku_ids:
        raise HTTPException(status_code=422, detail="存在未配置费率的启用 SKU")
    for rate in catalog.rate_entries:
        if rate.sku_id in sku_ids and not rate.allowed_plan_codes:
            raise HTTPException(status_code=422, detail="启用 SKU 必须至少配置一个可用会员方案")
        unknown_plans = set(rate.allowed_plan_codes or []) - plan_codes
        if unknown_plans:
            raise HTTPException(
                status_code=422,
                detail=f"SKU 费率包含不存在的会员方案：{', '.join(sorted(unknown_plans))}",
            )
    if any(package.active and package.price_fen <= 0 for package in catalog.credit_packages):
        raise HTTPException(status_code=422, detail="启用充值包的价格必须大于 0")
    now = datetime.now(timezone.utc)
    await db.execute(
        select(BillingCatalogVersion)
        .where(BillingCatalogVersion.status == "published", BillingCatalogVersion.id != catalog.id)
        .with_for_update()
    )
    await db.execute(
        update(BillingCatalogVersion)
        .where(BillingCatalogVersion.status == "published", BillingCatalogVersion.id != catalog.id)
        .values(status="retired")
    )
    catalog.status = "published"
    catalog.effective_at = now
    catalog.published_at = now
    catalog.published_by_admin_id = principal.user.id
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="BILLING_CATALOG_PUBLISH",
        target_type="billing_catalog",
        target_id=catalog.id,
        reason="发布计费目录",
        before_data={"status": "draft"},
        after_data={"status": "published", "version_key": catalog.version_key},
        idempotency_key=f"catalog-publish:{catalog.id}",
    )
    return _catalog_summary(catalog)


@router.get("/orders")
async def list_orders(
    status_filter: str = Query("", alias="status"),
    membership_id: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc)$"),
    _: AdminPrincipal = Depends(require_admin_permission("billing.read")),
    db: AsyncSession = Depends(get_db),
):
    latest_paid_order = aliased(Order)
    latest_paid_order_id = (
        select(latest_paid_order.id)
        .where(
            latest_paid_order.user_id == Order.user_id,
            latest_paid_order.status == "paid",
        )
        .order_by(latest_paid_order.paid_at.desc().nullslast(), latest_paid_order.created_at.desc())
        .limit(1)
        .correlate(Order)
        .scalar_subquery()
    )
    query = (
        select(Order, User, Subscription, latest_paid_order_id.label("latest_paid_order_id"))
        .join(User, User.id == Order.user_id)
        .outerjoin(Subscription, Subscription.user_id == User.id)
    )
    if status_filter:
        query = query.where(Order.status == status_filter)
    if membership_id:
        query = query.where(Order.membership_id == membership_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    ordering = Order.created_at.asc() if sort == "created_asc" else Order.created_at.desc()
    rows = (
        await db.execute(
            query.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    items = []
    for order, user, subscription, latest_order_id in rows:
        current_matches = bool(
            subscription
            and subscription.membership_id == order.membership_id
            and subscription.latest_order_id == order.id
        )
        requires_reconciliation = bool(
            order.product_type != "credit_package"
            and
            order.status == "paid"
            and order.id == latest_order_id
            and not current_matches
        )
        consistent = not requires_reconciliation
        items.append({
            "id": order.id,
            "user": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
            "membership_id": order.membership_id,
            "membership_name": order.membership_name,
            "billing_cycle": order.billing_cycle,
            "catalog_version_id": order.catalog_version_id,
            "product_type": order.product_type,
            "product_code": order.product_code,
            "price_fen": order.price_fen,
            "credit_amount": order.credit_amount,
            "amount": order.amount,
            "status": order.status,
            "created_at": order.created_at,
            "paid_at": order.paid_at,
            "current_subscription_matches_order": current_matches,
            "requires_reconciliation": requires_reconciliation,
            "subscription_consistent": consistent,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size, "sort": sort}


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    _: AdminPrincipal = Depends(require_admin_permission("billing.read")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Order, User, Subscription)
            .join(User, User.id == Order.user_id)
            .outerjoin(Subscription, Subscription.user_id == User.id)
            .where(Order.id == order_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="订单不存在")
    order, user, subscription = row
    latest_paid_order_id = (
        await db.execute(
            select(Order.id)
            .where(Order.user_id == order.user_id, Order.status == "paid")
            .order_by(Order.paid_at.desc().nullslast(), Order.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    invoice = (
        await db.execute(select(Invoice).where(Invoice.order_id == order.id))
    ).scalar_one_or_none()
    current_matches = bool(
        subscription
        and subscription.membership_id == order.membership_id
        and subscription.latest_order_id == order.id
    )
    requires_reconciliation = bool(
        order.product_type != "credit_package"
        and
        order.status == "paid"
        and latest_paid_order_id == order.id
        and not current_matches
    )
    return {
        "id": order.id,
        "user": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
        "membership_id": order.membership_id,
        "membership_name": order.membership_name,
        "billing_cycle": order.billing_cycle,
        "catalog_version_id": order.catalog_version_id,
        "product_type": order.product_type,
        "product_code": order.product_code,
        "price_fen": order.price_fen,
        "credit_amount": order.credit_amount,
        "amount": order.amount,
        "status": order.status,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "provider": order.provider,
        "provider_trade_no": order.provider_trade_no,
        "provider_status": order.provider_status,
        "paid_amount": order.paid_amount,
        "notify_received_at": order.notify_received_at,
        "subscription": {
            "id": subscription.id,
            "membership_id": subscription.membership_id,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "provider": subscription.provider,
            "latest_order_id": subscription.latest_order_id,
        } if subscription else None,
        "current_subscription_matches_order": current_matches,
        "requires_reconciliation": requires_reconciliation,
        "subscription_consistent": not requires_reconciliation,
        "invoice": {"id": invoice.id, "status": invoice.status} if invoice else None,
    }


@router.get("/invoices")
async def list_invoices(
    status_filter: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc)$"),
    _: AdminPrincipal = Depends(require_admin_permission("billing.read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Invoice, Order, User).join(Order, Order.id == Invoice.order_id).join(User, User.id == Invoice.user_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    ordering = Invoice.requested_at.asc() if sort == "created_asc" else Invoice.requested_at.desc()
    rows = (
        await db.execute(
            query.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": invoice.id,
                "order_id": order.id,
                "user": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
                "company_name": invoice.company_name,
                "tax_number": _mask_tax_number(invoice.tax_number),
                "email": mask_email(invoice.email),
                "status": invoice.status,
                "amount": order.amount,
                "requested_at": invoice.requested_at,
                "issued_at": invoice.issued_at,
                "invoice_number": invoice.invoice_number,
                "handled_at": invoice.handled_at,
            }
            for invoice, order, user in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "sort": sort,
    }


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    _: AdminPrincipal = Depends(require_admin_permission("billing.read")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Invoice, Order, User)
            .join(Order, Order.id == Invoice.order_id)
            .join(User, User.id == Invoice.user_id)
            .where(Invoice.id == invoice_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="发票申请不存在")
    invoice, order, user = row
    return {
        "id": invoice.id,
        "order": {"id": order.id, "amount": order.amount, "membership_name": order.membership_name, "status": order.status},
        "user": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
        "company_name": invoice.company_name,
        "tax_number": _mask_tax_number(invoice.tax_number),
        "email": mask_email(invoice.email),
        "status": invoice.status,
        "reject_reason": invoice.reject_reason,
        "requested_at": invoice.requested_at,
        "issued_at": invoice.issued_at,
        "invoice_number": invoice.invoice_number,
        "document_path": invoice.document_path,
        "handled_by_admin_id": invoice.handled_by_admin_id,
        "handled_at": invoice.handled_at,
        "sent_at": invoice.sent_at,
        "document_type": "application",
        "document_notice": "当前申请单不是正式税务电子发票",
    }


@router.post("/orders/{order_id}/reconcile-subscription")
async def reconcile_order_subscription(
    order_id: str,
    payload: BillingReasonRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("subscription.reconcile")),
    db: AsyncSession = Depends(get_db),
):
    existing = await _existing_audit(db, principal.user.id, "ORDER_SUBSCRIPTION_RECONCILE", idempotency_key)
    if existing:
        validate_idempotent_target(existing, target_type="order", target_id=order_id)
        prior = dict(existing.after_data or {})
        event_id = prior.pop("subscription_event_id", None)
        return {"order_id": order_id, "subscription": prior, "event_id": event_id, "idempotent_replay": True}
    order = (
        await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.product_type == "credit_package":
        raise HTTPException(status_code=409, detail="充值包订单不需要同步订阅")
    if order.status != "paid" or not order.paid_at:
        raise HTTPException(status_code=409, detail="只有已经真实支付的订单可以同步订阅")
    if order.paid_amount is not None and abs(float(order.paid_amount) - float(order.amount)) > 0.001:
        raise HTTPException(status_code=409, detail="订单实付金额与订单金额不一致，不能同步订阅")
    user = (
        await db.execute(
            select(User).where(User.id == order.user_id).options(
                selectinload(User.membership),
                selectinload(User.subscription),
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="订单关联用户不存在")
    before = _subscription_snapshot(user.subscription)
    previous_subscription = user.subscription
    previous_end = (
        previous_subscription.current_period_end
        if previous_subscription and previous_subscription.current_period_end
        else None
    )
    continuing_same_subscription = bool(
        previous_subscription
        and previous_subscription.status == "active"
        and previous_subscription.membership_id == order.membership_id
        and previous_end
        and previous_end > datetime.now(timezone.utc)
    )
    subscription = await activate_paid_subscription(db, user, order)
    if get_settings().billing_v2_enabled:
        await grant_subscription_credits(
            db,
            user,
            membership_id=order.membership_id,
            order_id=order.id,
            period_end=subscription.current_period_end,
            period_start=previous_end if continuing_same_subscription else subscription.current_period_start,
            catalog_version_id=order.catalog_version_id,
        )
    await synchronize_user_usage(db, user, for_update=True)
    after = _subscription_snapshot(subscription)
    event = SubscriptionEvent(
        user_id=user.id,
        subscription_id=subscription.id,
        event_type="admin_reconciled_paid_order",
        before_data=before,
        after_data=after,
        order_id=order.id,
        admin_user_id=principal.user.id,
        reason=payload.reason.strip(),
    )
    db.add(event)
    await db.flush()
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="ORDER_SUBSCRIPTION_RECONCILE",
        target_type="order",
        target_id=order.id,
        reason=payload.reason,
        before_data=before,
        after_data={**after, "subscription_event_id": event.id},
        idempotency_key=idempotency_key,
    )
    return {"order_id": order.id, "subscription": after, "event_id": event.id, "idempotent_replay": False}


async def _locked_invoice(db: AsyncSession, invoice_id: str) -> Invoice:
    invoice = (
        await db.execute(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
    ).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="发票申请不存在")
    return invoice


def _invoice_snapshot(invoice: Invoice) -> dict:
    return {
        "status": invoice.status,
        "reject_reason": invoice.reject_reason,
        "invoice_number": invoice.invoice_number,
        "document_path": invoice.document_path,
        "handled_by_admin_id": invoice.handled_by_admin_id,
        "handled_at": invoice.handled_at.isoformat() if invoice.handled_at else None,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
    }


@router.post("/invoices/{invoice_id}/accept")
async def accept_invoice(
    invoice_id: str,
    payload: BillingReasonRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("invoices.handle")),
    db: AsyncSession = Depends(get_db),
):
    existing = await _existing_audit(db, principal.user.id, "INVOICE_ACCEPT", idempotency_key)
    if existing:
        validate_idempotent_target(existing, target_type="invoice", target_id=invoice_id)
        return {"invoice_id": invoice_id, "invoice": existing.after_data, "idempotent_replay": True}
    invoice = await _locked_invoice(db, invoice_id)
    if invoice.status != "requested":
        raise HTTPException(status_code=409, detail="只有待处理的发票申请可以受理")
    before = _invoice_snapshot(invoice)
    invoice.status = "processing"
    invoice.handled_by_admin_id = principal.user.id
    invoice.handled_at = datetime.now(timezone.utc)
    after = _invoice_snapshot(invoice)
    await write_admin_audit(
        db, admin=principal.user, request=request, action="INVOICE_ACCEPT",
        target_type="invoice", target_id=invoice.id, reason=payload.reason,
        before_data=before, after_data=after, idempotency_key=idempotency_key,
    )
    return {"invoice_id": invoice.id, "invoice": after, "idempotent_replay": False}


@router.post("/invoices/{invoice_id}/reject")
async def reject_invoice(
    invoice_id: str,
    payload: InvoiceRejectRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("invoices.handle")),
    db: AsyncSession = Depends(get_db),
):
    existing = await _existing_audit(db, principal.user.id, "INVOICE_REJECT", idempotency_key)
    if existing:
        validate_idempotent_target(existing, target_type="invoice", target_id=invoice_id)
        return {"invoice_id": invoice_id, "invoice": existing.after_data, "idempotent_replay": True}
    invoice = await _locked_invoice(db, invoice_id)
    if invoice.status not in {"requested", "processing"}:
        raise HTTPException(status_code=409, detail="当前发票状态不能驳回")
    before = _invoice_snapshot(invoice)
    invoice.status = "rejected"
    invoice.reject_reason = payload.reason.strip()
    invoice.handled_by_admin_id = principal.user.id
    invoice.handled_at = datetime.now(timezone.utc)
    after = _invoice_snapshot(invoice)
    await write_admin_audit(
        db, admin=principal.user, request=request, action="INVOICE_REJECT",
        target_type="invoice", target_id=invoice.id, reason=payload.reason,
        before_data=before, after_data=after, idempotency_key=idempotency_key,
    )
    return {"invoice_id": invoice.id, "invoice": after, "idempotent_replay": False}


@router.post("/invoices/{invoice_id}/issue")
async def issue_invoice(
    invoice_id: str,
    payload: InvoiceIssueRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("invoices.handle")),
    db: AsyncSession = Depends(get_db),
):
    existing = await _existing_audit(db, principal.user.id, "INVOICE_ISSUE", idempotency_key)
    if existing:
        validate_idempotent_target(existing, target_type="invoice", target_id=invoice_id)
        return {"invoice_id": invoice_id, "invoice": existing.after_data, "idempotent_replay": True}
    invoice = await _locked_invoice(db, invoice_id)
    if invoice.status != "processing":
        raise HTTPException(status_code=409, detail="只有处理中的发票申请可以标记已开具")
    duplicate = (
        await db.execute(
            select(Invoice.id).where(
                Invoice.invoice_number == payload.invoice_number.strip(), Invoice.id != invoice.id
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="发票号码已经被其他申请使用")
    before = _invoice_snapshot(invoice)
    now = datetime.now(timezone.utc)
    invoice.status = "issued"
    invoice.invoice_number = payload.invoice_number.strip()
    invoice.document_path = payload.document_path.strip() if payload.document_path else None
    invoice.handled_by_admin_id = principal.user.id
    invoice.handled_at = now
    invoice.issued_at = now
    invoice.reject_reason = ""
    after = _invoice_snapshot(invoice)
    await write_admin_audit(
        db, admin=principal.user, request=request, action="INVOICE_ISSUE",
        target_type="invoice", target_id=invoice.id, reason=payload.reason,
        before_data=before, after_data=after, idempotency_key=idempotency_key,
    )
    return {"invoice_id": invoice.id, "invoice": after, "idempotent_replay": False}
