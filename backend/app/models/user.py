"""用户、会员、用量模型。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Membership(Base):
    """会员方案。"""
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=lambda: f"membership-{uuid.uuid4().hex[:12]}")
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # Free / Pro / Team
    rank: Mapped[int] = mapped_column(Integer, default=0)  # 档位序号
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly / yearly
    processing_minutes: Mapped[int] = mapped_column(Integer, default=60)  # 处理分钟数配额
    ai_image_quota: Mapped[int] = mapped_column(Integer, default=10)  # AI 生图配额
    ai_video_quota: Mapped[int] = mapped_column(Integer, default=5)  # AI 生视频配额
    storage_gb: Mapped[int] = mapped_column(Integer, default=5)  # 存储容量 GB
    export_quota: Mapped[int] = mapped_column(Integer, default=10)  # 导出次数配额
    price: Mapped[float] = mapped_column(Float, default=0.0)  # 价格（元）
    payment_method: Mapped[str] = mapped_column(String(50), nullable=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="membership")


class User(Base):
    """用户。"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=lambda: f"user-{uuid.uuid4().hex[:12]}")
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_initial: Mapped[str] = mapped_column(String(4), default="U")  # 头像首字母
    membership_id: Mapped[str] = mapped_column(String(50), ForeignKey("memberships.id"), default="membership-free")
    notify_asset_processing: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_script_generation: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    membership: Mapped["Membership"] = relationship("Membership", back_populates="users")
    usage: Mapped["Usage"] = relationship("Usage", back_populates="user", uselist=False, cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )  # type: ignore


class Usage(Base):
    """用量统计。"""
    __tablename__ = "usages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=lambda: f"usage-{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id"), unique=True, nullable=False)
    processing_minutes_used: Mapped[int] = mapped_column(Integer, default=0)
    ai_image_used: Mapped[int] = mapped_column(Integer, default=0)
    ai_video_used: Mapped[int] = mapped_column(Integer, default=0)
    storage_used_mb: Mapped[float] = mapped_column(Float, default=0.0)
    export_used: Mapped[int] = mapped_column(Integer, default=0)
    billing_cycle_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    billing_cycle_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship("User", back_populates="usage")
