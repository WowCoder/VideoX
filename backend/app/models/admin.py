"""运营后台管理员、可撤销会话与不可删除审计日志。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    """独立于普通业务用户的后台管理员账号。"""

    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin', 'operator', 'finance')",
            name="ck_admin_users_role",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_admin_users_status",
        ),
        CheckConstraint("token_version >= 1", name="ck_admin_users_token_version"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"admin-{uuid.uuid4().hex[:12]}"
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="operator", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mfa_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    sessions: Mapped[list["AdminSession"]] = relationship(
        "AdminSession", back_populates="admin_user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AdminAuditLog"]] = relationship(
        "AdminAuditLog", back_populates="admin_user"
    )


class AdminSession(Base):
    """后台刷新会话；Refresh Token 只保存哈希，可单独撤销。"""

    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index("ix_admin_sessions_admin_expires", "admin_user_id", "expires_at"),
        Index("ix_admin_sessions_active", "revoked_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"admin-session-{uuid.uuid4().hex[:16]}"
    )
    admin_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    admin_user: Mapped[AdminUser] = relationship("AdminUser", back_populates="sessions")


class AdminAuditLog(Base):
    """后台敏感查看和写操作的追加式审计记录。"""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        UniqueConstraint(
            "admin_user_id", "action", "idempotency_key",
            name="uq_admin_audit_idempotency",
        ),
        Index("ix_admin_audit_admin_created", "admin_user_id", "created_at"),
        Index("ix_admin_audit_target", "target_type", "target_id"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"admin-audit-{uuid.uuid4().hex[:16]}"
    )
    admin_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    before_data: Mapped[dict] = mapped_column(JSON, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="succeeded", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    admin_user: Mapped[AdminUser] = relationship("AdminUser", back_populates="audit_logs")


class QuotaAdjustment(Base):
    """管理员发放的正向额度补偿，不篡改用户已使用计数。"""

    __tablename__ = "quota_adjustments"
    __table_args__ = (
        CheckConstraint(
            "quota_type IN ('processing_seconds', 'ai_image', 'ai_video', 'export')",
            name="ck_quota_adjustments_type",
        ),
        CheckConstraint("amount > 0", name="ck_quota_adjustments_positive"),
        UniqueConstraint(
            "admin_user_id", "idempotency_key", name="uq_quota_adjustments_idempotency"
        ),
        Index("ix_quota_adjustments_user_active", "user_id", "effective_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"quota-adjustment-{uuid.uuid4().hex[:16]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quota_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    related_job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    admin_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
