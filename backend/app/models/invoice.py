"""已支付订单的开票申请记录。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("order_id", name="uq_invoices_order_id"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"invoice-{uuid.uuid4().hex[:12]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_number: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    order: Mapped["Order"] = relationship("Order")  # type: ignore
