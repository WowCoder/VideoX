"""用户级全局素材、项目关联与统一素材片段模型。"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


EMBEDDING_DIM = 1024


class Asset(Base):
    """全局素材；一个物理媒体对象只属于用户，不属于单个项目。"""

    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_owner_media_created", "owner_id", "media_type", "created_at"),
        Index("ix_assets_owner_source_created", "owner_id", "source_type", "created_at"),
        Index("ix_assets_owner_processing_created", "owner_id", "processing_status", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"asset-{uuid.uuid4().hex[:12]}"
    )
    owner_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), default="video", index=True)
    source_type: Mapped[str] = mapped_column(String(30), default="upload", index=True)
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    processing_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_size_mb: Mapped[float] = mapped_column(Float, default=0.0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    recognition: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ai_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    owner: Mapped["User"] = relationship("User", back_populates="assets")  # type: ignore[name-defined]
    segments: Mapped[list["AssetSegment"]] = relationship(
        "AssetSegment", back_populates="asset", cascade="all, delete-orphan"
    )
    project_links: Mapped[list["ProjectAssetLink"]] = relationship(
        "ProjectAssetLink", back_populates="asset", cascade="all, delete-orphan"
    )


class ProjectAssetLink(Base):
    """项目对全局素材的逻辑引用。"""

    __tablename__ = "project_asset_links"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_id", "role", name="uq_project_asset_role"),
        Index("ix_project_asset_links_project_linked", "project_id", "linked_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"asset-link-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(30), default="source")
    linked_by: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="asset_links")  # type: ignore[name-defined]
    asset: Mapped[Asset] = relationship("Asset", back_populates="project_links")


class AssetSegment(Base):
    """可检索的素材片段；图片使用一条 start/end 均为 0 的静态片段。"""

    __tablename__ = "asset_segments"
    __table_args__ = (
        Index(
            "ix_asset_segments_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"segment-{uuid.uuid4().hex[:12]}"
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    recognition: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_version: Mapped[int] = mapped_column(Integer, default=1)
    embedding_status: Mapped[str] = mapped_column(String(20), default="missing", index=True)
    embedding_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    asset: Mapped[Asset] = relationship("Asset", back_populates="segments")

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)
