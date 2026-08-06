"""项目素材箱媒体索引。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectMediaItem(Base):
    """把来源素材和 AI 生成媒体逻辑导入剪辑项目，不复制底层文件。"""

    __tablename__ = "project_media_items"
    __table_args__ = (
        UniqueConstraint("project_id", "dedupe_key", name="uq_project_media_project_key"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"media-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # source_asset / ai_image / ai_video / ai_effect_video
    dedupe_key: Mapped[str] = mapped_column(String(1100), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_script_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_shot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship(  # type: ignore
        "Project", back_populates="media_items", foreign_keys=[project_id]
    )
    asset: Mapped["Asset | None"] = relationship("Asset", foreign_keys=[asset_id])  # type: ignore

