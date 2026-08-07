"""剪辑项目内的用户可见版本。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CutVersion(Base):
    """一个剪辑项目可以包含多个独立时间线版本。"""

    __tablename__ = "cut_versions"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_cut_version_project_name"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"cut-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_script_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="AI 初剪生成中")
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="16:9")
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    timeline_version: Mapped[int] = mapped_column(Integer, default=0)
    timeline_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship("Project", back_populates="cut_versions")  # type: ignore
    snapshot_script: Mapped["Script | None"] = relationship(  # type: ignore
        "Script", foreign_keys=[snapshot_script_id]
    )
