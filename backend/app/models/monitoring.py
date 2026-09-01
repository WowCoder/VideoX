"""用户活跃与低频系统资源快照。"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserDailyActivity(Base):
    """按北京时间自然日去重的用户活跃记录。"""

    __tablename__ = "user_daily_activities"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_date", name="uq_user_daily_activity_user_date"),
        Index("ix_user_daily_activities_date_user", "activity_date", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"activity-{uuid.uuid4().hex[:16]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SystemMetricSnapshot(Base):
    """宿主机或容器的低频资源采集快照。"""

    __tablename__ = "system_metric_snapshots"
    __table_args__ = (
        Index("ix_system_metric_node_collected", "node_name", "collected_at"),
        Index("ix_system_metric_status_collected", "collection_status", "collected_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"system-metric-{uuid.uuid4().hex[:16]}"
    )
    node_name: Mapped[str] = mapped_column(String(100), nullable=False, default="primary", index=True)
    metric_scope: Mapped[str] = mapped_column(String(30), nullable=False, default="container")
    collection_source: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    collection_status: Mapped[str] = mapped_column(String(20), nullable=False, default="succeeded")
    load_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_free_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
