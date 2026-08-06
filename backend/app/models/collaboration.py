"""项目成员与邀请模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectMember(Base):
    """已加入项目的协作者；项目所有者仍以 Project.owner_id 为准。"""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        Index("ix_project_members_user_project", "user_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"member-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    invited_by_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship("Project", back_populates="project_members")  # type: ignore
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore
    invited_by: Mapped["User | None"] = relationship("User", foreign_keys=[invited_by_id])  # type: ignore


class ProjectInvitation(Base):
    """项目邀请。数据库只保存 token 哈希，原始邀请凭证只通过创建响应返回。"""

    __tablename__ = "project_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_project_invitations_token_hash"),
        Index("ix_project_invitations_project_email", "project_id", "email"),
        Index("ix_project_invitations_status_expires", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"invite-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    inviter_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship("Project", back_populates="project_invitations")  # type: ignore
    inviter: Mapped["User | None"] = relationship("User", foreign_keys=[inviter_id])  # type: ignore
    accepted_user: Mapped["User | None"] = relationship("User", foreign_keys=[accepted_user_id])  # type: ignore
