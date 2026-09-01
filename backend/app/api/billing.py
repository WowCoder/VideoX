"""会员与支付路由：会员方案/升级订单/支付宝回调/订单列表/用量。

路由前缀：/api/billing
所有第三方支付凭证未配置时返回明确的提示信息。
"""

import logging
import io
import os
import textwrap
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, Membership
from app.models.order import Order
from app.models.invoice import Invoice
from app.schemas.auth import MembershipOut, SubscriptionOut, UsageOut
from app.services.subscriptions import activate_paid_subscription, ensure_user_subscription
from app.services.quotas import synchronize_user_usage

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 请求 / 响应模型 ──

class UpgradeRequest(BaseModel):
    """升级订单请求。"""
    membership_id: str = Field(..., description="目标会员方案 ID")
    billing_cycle: Literal["monthly", "yearly"] = Field(
        "monthly", description="计费周期：monthly / yearly"
    )


class UpgradeResponse(BaseModel):
    """升级订单响应。"""
    order_id: str
    message: str
    pay_url: str = ""


class OrderOut(BaseModel):
    """订单信息。"""
    order_id: str
    user_id: str
    membership_id: str
    membership_name: str
    billing_cycle: str
    amount: float
    status: str  # pending / paid / cancelled
    pay_url: str
    created_at: str

    class Config:
        from_attributes = True


class AlipayNotifyResponse(BaseModel):
    """支付宝回调响应。"""
    result: str


class InvoiceCreateRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    company_name: str = Field(..., min_length=2, max_length=200)
    tax_number: str = Field(..., min_length=8, max_length=30, pattern="^[0-9A-Za-z]+$")
    email: EmailStr


class InvoiceOut(BaseModel):
    id: str
    order_id: str
    company_name: str
    tax_number: str
    email: str
    status: str
    reject_reason: str
    requested_at: datetime
    issued_at: datetime | None = None
    order_amount: float
    membership_name: str
    document_type: str = "application"
    document_notice: str = "当前仅提供开票申请单，不是税务电子发票"


# ── 路由 ──

@router.get("/plans", response_model=list[MembershipOut])
async def list_plans(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取会员方案列表。

    从数据库 memberships 表读取所有方案，按 rank 排序。
    """
    result = await db.execute(select(Membership).order_by(Membership.rank))
    return [MembershipOut.model_validate(m) for m in result.scalars().all()]


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户已经过到期校验的订阅状态。"""
    subscription = user.subscription or await ensure_user_subscription(db, user)
    return SubscriptionOut.model_validate(subscription)


@router.post("/upgrade", response_model=UpgradeResponse)
async def create_upgrade_order(
    req: UpgradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建升级订单。

    检查用户当前会员，创建订单记录。
    如果配置了支付宝：生成支付链接。
    未配置支付宝：返回 pay_url 为空的订单信息。
    """
    if not settings.has_alipay:
        raise HTTPException(status_code=503, detail="支付功能未配置，请联系管理员")

    # 查找目标会员方案
    result = await db.execute(select(Membership).where(Membership.id == req.membership_id))
    target_membership = result.scalar_one_or_none()
    if not target_membership:
        raise HTTPException(status_code=404, detail="会员方案不存在")
    if target_membership.rank <= 0:
        raise HTTPException(status_code=400, detail="Free 方案无需购买")

    # 检查是否已持有更高或同等档位
    current_result = await db.execute(
        select(Membership).where(Membership.id == user.membership_id)
    )
    current_membership = current_result.scalar_one_or_none()
    if current_membership and current_membership.rank > target_membership.rank:
        raise HTTPException(status_code=400, detail="暂不支持在线降级会员方案")

    # 计算金额
    amount = target_membership.price
    if req.billing_cycle == "yearly" and target_membership.billing_cycle == "monthly":
        # 年付按 10 个月计算（2 个月优惠）
        amount = target_membership.price * 10

    # 创建订单
    order = Order(
        user_id=user.id,
        membership_id=req.membership_id,
        membership_name=target_membership.name,
        billing_cycle=req.billing_cycle,
        amount=amount,
        status="pending",
    )
    db.add(order)
    await db.flush()
    try:
        pay_url = _generate_alipay_pay_url(order.id, amount, target_membership.name)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    if not pay_url:
        raise HTTPException(status_code=503, detail="支付链接生成失败，请检查支付宝配置")
    order.pay_url = pay_url
    is_renewal = bool(current_membership and current_membership.rank == target_membership.rank)
    logger.info(
        "%s订单已创建：%s 用户 %s -> %s",
        "续费" if is_renewal else "升级",
        order.id,
        user.id,
        target_membership.name,
    )

    return UpgradeResponse(
        order_id=order.id,
        message=f"{'续费' if is_renewal else '升级'}订单已创建，请前往支付宝完成支付",
        pay_url=order.pay_url,
    )


@router.post("/alipay/notify", response_model=AlipayNotifyResponse)
async def alipay_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """支付宝异步回调通知。

    支付宝在用户完成支付后向此接口发送 POST 请求。
    验证签名后更新用户会员状态。
    """
    # 解析支付宝回调数据
    form_data = await request.form()
    notify_data = {k: v for k, v in form_data.items()}

    # 验证签名（简化处理：生产环境应使用支付宝 SDK 验签）
    if settings.has_alipay:
        verified = _verify_alipay_sign(notify_data)
        if not verified:
            logger.warning("支付宝回调验签失败")
            return AlipayNotifyResponse(result="fail")
    else:
        logger.warning("支付宝未配置，忽略回调")
        return AlipayNotifyResponse(result="fail")

    # 获取订单信息
    order_id = notify_data.get("out_trade_no", "")
    trade_status = notify_data.get("trade_status", "")
    result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()

    if not order:
        logger.warning("支付宝回调：订单不存在 %s", order_id)
        return AlipayNotifyResponse(result="fail")

    order.provider = "alipay"
    order.provider_status = str(trade_status or "")[:50] or None
    order.notify_received_at = _utcnow()

    # 非成功状态只记录通知，不激活订阅。
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return AlipayNotifyResponse(result="success")

    trade_no = str(notify_data.get("trade_no") or "").strip()
    total_amount_raw = str(notify_data.get("total_amount") or "").strip()
    try:
        paid_amount = float(total_amount_raw)
    except ValueError:
        logger.warning("支付宝回调金额无效：订单 %s", order.id)
        return AlipayNotifyResponse(result="fail")
    if abs(paid_amount - float(order.amount)) > 0.001:
        logger.warning("支付宝回调金额不匹配：订单 %s", order.id)
        return AlipayNotifyResponse(result="fail")
    if not trade_no:
        logger.warning("支付宝回调缺少交易号：订单 %s", order.id)
        return AlipayNotifyResponse(result="fail")
    trade_owner = (
        await db.execute(
            select(Order.id).where(Order.provider_trade_no == trade_no, Order.id != order.id)
        )
    ).scalar_one_or_none()
    if trade_owner:
        logger.error("支付宝交易号重复绑定：%s", trade_no)
        return AlipayNotifyResponse(result="fail")
    order.provider_trade_no = trade_no
    order.paid_amount = paid_amount

    # 支付宝可能重复投递同一回调；已支付订单不得再次延长订阅。
    if order.status == "paid":
        return AlipayNotifyResponse(result="success")

    user = (
        await db.execute(
            select(User)
            .where(User.id == order.user_id)
            .options(selectinload(User.membership), selectinload(User.subscription))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not user:
        logger.error("支付宝回调：订单用户不存在 %s", order.user_id)
        return AlipayNotifyResponse(result="fail")

    await activate_paid_subscription(db, user, order)
    await synchronize_user_usage(db, user, for_update=True)
    logger.info("用户 %s 会员订阅已更新至 %s", user.id, order.membership_id)

    # 更新订单状态
    order.status = "paid"
    order.paid_at = _utcnow()

    return AlipayNotifyResponse(result="success")


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的订单列表。"""
    result = await db.execute(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
    )
    return [
        OrderOut(
            order_id=order.id,
            user_id=order.user_id,
            membership_id=order.membership_id,
            membership_name=order.membership_name,
            billing_cycle=order.billing_cycle,
            amount=order.amount,
            status=order.status,
            pay_url=order.pay_url,
            created_at=order.created_at.isoformat(),
        )
        for order in result.scalars().all()
    ]


def _invoice_out(invoice: Invoice, order: Order) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        order_id=invoice.order_id,
        company_name=invoice.company_name,
        tax_number=invoice.tax_number,
        email=invoice.email,
        status=invoice.status,
        reject_reason=invoice.reject_reason or "",
        requested_at=invoice.requested_at,
        issued_at=invoice.issued_at,
        order_amount=order.amount,
        membership_name=order.membership_name,
    )


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Invoice, Order)
            .join(Order, Invoice.order_id == Order.id)
            .where(Invoice.user_id == user.id)
            .order_by(Invoice.requested_at.desc())
        )
    ).all()
    return [_invoice_out(invoice, order) for invoice, order in rows]


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
async def create_invoice_application(
    req: InvoiceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = (
        await db.execute(
            select(Order)
            .where(Order.id == req.order_id, Order.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "paid" or not order.paid_at:
        raise HTTPException(status_code=400, detail="只有已支付订单可以提交开票申请")
    existing = (
        await db.execute(select(Invoice).where(Invoice.order_id == order.id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="该订单已提交开票申请")

    invoice = Invoice(
        user_id=user.id,
        order_id=order.id,
        company_name=req.company_name.strip(),
        tax_number=req.tax_number.strip().upper(),
        email=str(req.email).strip().lower(),
        status="requested",
    )
    db.add(invoice)
    await db.flush()
    return _invoice_out(invoice, order)


def _invoice_application_pdf(invoice: Invoice, order: Order) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font_candidates = [
        settings.subtitle_font_path,
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((path for path in font_candidates if path and os.path.isfile(path)), None)
    if not font_path:
        raise RuntimeError("服务器缺少可用于申请单 PDF 的中文字体")

    title_font = ImageFont.truetype(font_path, 38)
    body_font = ImageFont.truetype(font_path, 24)
    warning_font = ImageFont.truetype(font_path, 22)
    paid_at = order.paid_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if order.paid_at else "-"
    requested_at = invoice.requested_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "OpenVMA 开票申请单",
        "重要声明：本文件仅记录开票申请，不是增值税发票或电子发票，",
        "不具备报销、入账或税务抵扣效力。正式发票需由税务开票服务另行签发。",
        "",
        f"申请编号：{invoice.id}",
        f"申请状态：待处理（requested）",
        f"申请时间：{requested_at}",
        "",
        f"订单编号：{order.id}",
        f"支付时间：{paid_at}",
        f"购买方案：{order.membership_name} / {order.billing_cycle}",
        f"实付金额：人民币 ¥{order.amount:.2f}",
        "",
        f"企业名称：{invoice.company_name}",
        f"纳税人识别号：{invoice.tax_number}",
        f"接收邮箱：{invoice.email}",
    ]
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    draw.rounded_rectangle((60, 60, 1180, 1694), radius=20, outline="#D8DEE9", width=3)
    y = 110
    for index, line in enumerate(lines):
        wrapped = textwrap.wrap(line, width=52) or [""]
        for wrapped_line in wrapped:
            font = title_font if index == 0 else warning_font if index in {1, 2} else body_font
            color = "#182033" if index == 0 else "#B45309" if index in {1, 2} else "#374151"
            draw.text((100, y), wrapped_line, fill=color, font=font)
            y += 54 if index == 0 else 40
        if index in {0, 2, 7, 12}:
            y += 18
    output = io.BytesIO()
    page.save(output, format="PDF", resolution=144)
    return output.getvalue()


@router.get("/invoices/{invoice_id}/application.pdf")
async def download_invoice_application(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Invoice, Order)
            .join(Order, Invoice.order_id == Order.id)
            .where(Invoice.id == invoice_id, Invoice.user_id == user.id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="开票申请不存在")
    invoice, order = row
    try:
        content = _invoice_application_pdf(invoice, order)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    filename = quote(f"OpenVMA-开票申请单-{invoice.id}.pdf")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/usage", response_model=UsageOut)
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户用量。

    与 /api/generate/usage 功能一致，在 billing 模块也暴露此端点。
    """
    usage = await synchronize_user_usage(db, user)
    return UsageOut.model_validate(usage)


# ── 支付宝辅助函数（预留接口，凭证填入即生效）──

def _generate_alipay_pay_url(order_id: str, amount: float, subject: str) -> str:
    """生成支付宝支付链接。

    使用 python-alipay-sdk 生成电脑网站支付 (alipay.trade.page.pay) URL。
    SDK 未安装或配置错误时抛出异常，不生成占位支付地址。

    配置项（.env）：
        ALIPAY_APP_ID         支付宝应用 ID
        ALIPAY_PRIVATE_KEY    应用私钥
        ALIPAY_PUBLIC_KEY     支付宝公钥
        ALIPAY_SANDBOX        是否沙箱环境
        ALIPAY_NOTIFY_URL     异步回调地址
        ALIPAY_RETURN_URL     同步跳转地址
    """
    try:
        from alipay import AliPay

        alipay_client = AliPay(
            appid=settings.alipay_app_id,
            app_notify_url=settings.alipay_notify_url,
            app_private_key_string=settings.alipay_private_key,
            alipay_public_key_string=settings.alipay_public_key,
            sign_type="RSA2",
            debug=settings.alipay_sandbox,
        )

        pay_url = alipay_client.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=f"{amount:.2f}",
            subject=subject,
            return_url=settings.alipay_return_url,
            notify_url=settings.alipay_notify_url,
        )

        base_url = (
            "https://openapi.alipaydev.com/gateway.do"
            if settings.alipay_sandbox
            else "https://openapi.alipay.com/gateway.do"
        )
        return f"{base_url}?{pay_url}"
    except ImportError:
        raise RuntimeError("python-alipay-sdk 未安装")
    except Exception as e:
        logger.error("生成支付宝链接失败：%s", e)
        raise RuntimeError(f"生成支付宝链接失败：{e}")


def _verify_alipay_sign(notify_data: dict) -> bool:
    """验证支付宝回调签名。

    使用 python-alipay-sdk 验签。
    SDK 未安装时拒绝验签。

    生产环境必须安装 SDK 并正确验签，否则存在安全风险。
    """
    try:
        from alipay import AliPay

        alipay_client = AliPay(
            appid=settings.alipay_app_id,
            app_notify_url=settings.alipay_notify_url,
            app_private_key_string=settings.alipay_private_key,
            alipay_public_key_string=settings.alipay_public_key,
            sign_type="RSA2",
            debug=settings.alipay_sandbox,
        )

        sign = notify_data.pop("sign", "")
        sign_type = notify_data.pop("sign_type", "")
        return alipay_client.verify(notify_data, sign)
    except ImportError:
        logger.error("python-alipay-sdk 未安装，无法验证支付宝签名")
        return False
    except Exception as e:
        logger.error("支付宝验签失败：%s", e)
        return False
