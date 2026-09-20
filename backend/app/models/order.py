"""会员升级订单模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"order-{uuid.uuid4().hex[:12]}"
    )
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id"), nullable=False, index=True)
    membership_id: Mapped[str] = mapped_column(String(50), ForeignKey("memberships.id"), nullable=False)
    membership_name: Mapped[str] = mapped_column(String(100), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # 计费 V2 商品与目录快照；旧订单为空，读取时继续使用 legacy 字段。
    catalog_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_type: Mapped[str] = mapped_column(String(30), default="membership", nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price_fen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    pay_url: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="alipay")
    provider_trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    provider_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    notify_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
