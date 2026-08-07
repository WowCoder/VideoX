"""素材与片段模型。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# BGE-M3 与 DashScope text-embedding-v3 均可输出 1024 维，但向量空间不能混用。
EMBEDDING_DIM = 1024


class Asset(Base):
    """素材（视频文件）。

    对应详设 4.2 Asset：
    id, projectId, name, duration, status, uploadedAt, source, variant, clips
    """
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"asset-{uuid.uuid4().hex[:12]}")
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False, index=True)
    imported_from_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0)  # 秒
    status: Mapped[str] = mapped_column(String(50), default="处理中")
    # status: 处理中 / AI 处理中 / 处理完成 / 处理失败
    source: Mapped[str] = mapped_column(String(100), default="用户上传")  # 来源
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    media_type: Mapped[str] = mapped_column(String(20), default="video", index=True)
    # media_type: video / audio
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)  # MinIO 对象 key
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=True)  # 代表帧对象 key
    file_size_mb: Mapped[float] = mapped_column(Float, default=0.0)
    # ── 媒体元信息 ──
    resolution: Mapped[str] = mapped_column(String(20), nullable=True)  # "1920x1080"
    fps: Mapped[float] = mapped_column(Float, default=25.0)
    codec: Mapped[str] = mapped_column(String(50), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ── 处理结果 ──
    transcript: Mapped[str] = mapped_column(Text, nullable=True)  # 完整转写文本
    ocr_text: Mapped[str] = mapped_column(Text, nullable=True)  # OCR 识别文本
    tags: Mapped[list] = mapped_column(JSON, default=list)  # 自动标签
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="assets")  # type: ignore
    imported_from: Mapped["Asset | None"] = relationship(
        "Asset", remote_side=[id], foreign_keys=[imported_from_asset_id]
    )
    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="asset", cascade="all, delete-orphan")


class Clip(Base):
    """素材片段（镜头切分结果）。

    对应详设 Asset.clips 中的片段，带语义向量用于检索。
    """
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"clip-{uuid.uuid4().hex[:12]}")
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False, index=True)
    # ── 时间范围 ──
    start_time: Mapped[float] = mapped_column(Float, default=0.0)  # 秒
    end_time: Mapped[float] = mapped_column(Float, default=0.0)  # 秒
    duration: Mapped[float] = mapped_column(Float, default=0.0)  # 秒
    # ── 内容描述 ──
    title: Mapped[str] = mapped_column(String(200), default="")  # 片段标题
    transcript_segment: Mapped[str] = mapped_column(Text, default="")  # 该片段的转写文本
    ocr_segment: Mapped[str] = mapped_column(Text, default="")  # 该片段的 OCR 文本
    # ── 画面分析 ──
    scene_type: Mapped[str] = mapped_column(String(50), nullable=True)  # 场景类型
    shot_type: Mapped[str] = mapped_column(String(50), nullable=True)  # 镜头类型（远景/中景/近景等）
    camera_motion: Mapped[str] = mapped_column(String(50), nullable=True)  # 运镜方式
    persons: Mapped[list] = mapped_column(JSON, default=list)  # 识别到的人物
    objects: Mapped[list] = mapped_column(JSON, default=list)  # 识别到的物品
    # ── 语义向量 ──
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=True)
    embedding_version: Mapped[int] = mapped_column(Integer, default=1)
    embedding_status: Mapped[str] = mapped_column(String(20), default="missing", index=True)
    embedding_source_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── 缩略图 ──
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=True)  # MinIO 缩略图 key
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    # ── 质量评分 ──
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="clips")
