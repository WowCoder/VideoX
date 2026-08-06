"""用户通知模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    """由真实任务终态或后端业务事件产生的站内通知。"""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"notification-{uuid.uuid4().hex[:12]}"
    )
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(30), default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    user: Mapped["User"] = relationship("User", back_populates="notifications")  # type: ignore

