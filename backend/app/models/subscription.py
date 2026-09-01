"""用户当前会员订阅模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    """每个用户一条当前订阅记录；历史支付保留在 orders 表。"""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        Index("ix_subscriptions_user_id", "user_id"),
        CheckConstraint(
            "status IN ('active', 'internal', 'past_due', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly', 'permanent')",
            name="ck_subscriptions_billing_cycle",
        ),
        CheckConstraint(
            "current_period_end IS NULL OR current_period_end > current_period_start",
            name="ck_subscriptions_period_order",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"subscription-{uuid.uuid4().hex[:12]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("memberships.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="permanent", nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="system", nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latest_order_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="subscription")  # type: ignore[name-defined]
    membership: Mapped["Membership"] = relationship("Membership")  # type: ignore[name-defined]
    latest_order: Mapped["Order | None"] = relationship("Order")  # type: ignore[name-defined]


class SubscriptionEvent(Base):
    """订阅变更的业务级不可变流水。"""

    __tablename__ = "subscription_events"
    __table_args__ = (Index("ix_subscription_events_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"subscription-event-{uuid.uuid4().hex[:16]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    before_data: Mapped[dict] = mapped_column(JSON, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, default=dict)
    order_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    admin_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
