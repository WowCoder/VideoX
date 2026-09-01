"""运营后台订单、订阅一致性和发票查询。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.audit import validate_idempotent_target, write_admin_audit
from app.admin.redaction import mask_email
from app.database import get_db
from app.models.invoice import Invoice
from app.models.admin import AdminAuditLog
from app.models.order import Order
from app.models.subscription import Subscription, SubscriptionEvent
from app.models.user import User
from app.services.quotas import synchronize_user_usage
from app.services.subscriptions import activate_paid_subscription


router = APIRouter()


class BillingReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class InvoiceRejectRequest(BillingReasonRequest):
    pass


class InvoiceIssueRequest(BillingReasonRequest):
    invoice_number: str = Field(..., min_length=3, max_length=100)
    document_path: str | None = Field(None, max_length=1000)


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


@router.get("/orders")
async def list_orders(
    status_filter: str = Query("", alias="status"),
    membership_id: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
    rows = (
        await db.execute(
            query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
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
            "amount": order.amount,
            "status": order.status,
            "created_at": order.created_at,
            "paid_at": order.paid_at,
            "current_subscription_matches_order": current_matches,
            "requires_reconciliation": requires_reconciliation,
            "subscription_consistent": consistent,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


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
    _: AdminPrincipal = Depends(require_admin_permission("billing.read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Invoice, Order, User).join(Order, Order.id == Invoice.order_id).join(User, User.id == Invoice.user_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Invoice.requested_at.desc()).offset((page - 1) * page_size).limit(page_size)
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
    subscription = await activate_paid_subscription(db, user, order)
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
