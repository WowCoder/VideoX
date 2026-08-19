"""项目唯一脚本、场景、镜头、候选和媒体版本模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_visual_config() -> dict:
    return {
        "stylePreset": "brand-tech",
        "aspectRatio": "16:9",
        "palette": "冷灰蓝",
        "cameraRhythm": "稳定推进",
        "consistencyEnabled": True,
        "generationPolicy": "优先使用项目素材，缺失镜头由 AI 补齐",
        "references": {"characters": [], "objects": [], "spaces": []},
    }


class Script(Base):
    """项目唯一主脚本；数据库唯一约束禁止项目产生第二份业务脚本。"""

    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("project_id", name="uq_scripts_project_id"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"script-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="editing", index=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(20), default="blank")
    visual_config: Mapped[dict] = mapped_column(JSON, default=_default_visual_config)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship("Project", back_populates="script")  # type: ignore[name-defined]
    units: Mapped[list["ScriptUnit"]] = relationship(
        "ScriptUnit", back_populates="script", cascade="all, delete-orphan", order_by="ScriptUnit.index"
    )


class ScriptUnit(Base):
    """脚本场景；narration_text 是字幕派生的唯一源文本。"""

    __tablename__ = "script_units"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"scene-{uuid.uuid4().hex[:12]}"
    )
    script_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, default=0)
    outline: Mapped[str] = mapped_column(String(200), default="")
    narration_text: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="editing")
    estimated_duration_ms: Mapped[int] = mapped_column(Integer, default=8000)
    notes: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    script: Mapped[Script] = relationship("Script", back_populates="units")
    shots: Mapped[list["Shot"]] = relationship(
        "Shot", back_populates="unit", cascade="all, delete-orphan", order_by="Shot.index"
    )


class Shot(Base):
    """成片中的最小叙事和编辑单元。"""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"shot-{uuid.uuid4().hex[:12]}"
    )
    unit_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("script_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="editing")
    visual_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    segment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("asset_segments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    selected_media_version_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "shot_media_versions.id",
            name="fk_shots_selected_media_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    source_start_ms: Mapped[int] = mapped_column(Integer, default=0)
    source_end_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=8000)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    transform: Mapped[dict] = mapped_column(JSON, default=dict)
    adjust: Mapped[dict] = mapped_column(JSON, default=dict)
    audio_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    subtitle_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    transition: Mapped[dict] = mapped_column(JSON, default=dict)
    motion: Mapped[dict] = mapped_column(JSON, default=dict)
    subtitle_text: Mapped[str] = mapped_column(Text, default="")
    subtitle_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    subtitle_source_revision: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    sketch_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    unit: Mapped[ScriptUnit] = relationship("ScriptUnit", back_populates="shots")
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate", back_populates="shot", cascade="all, delete-orphan", order_by="Candidate.score.desc()"
    )
    media_versions: Mapped[list["ShotMediaVersion"]] = relationship(
        "ShotMediaVersion",
        back_populates="shot",
        cascade="all, delete-orphan",
        foreign_keys="ShotMediaVersion.shot_id",
        order_by="ShotMediaVersion.created_at.desc()",
    )
    selected_media_version: Mapped["ShotMediaVersion | None"] = relationship(
        "ShotMediaVersion",
        foreign_keys=[selected_media_version_id],
        post_update=True,
    )


class Candidate(Base):
    """规范化的镜头素材匹配候选。"""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"candidate-{uuid.uuid4().hex[:12]}"
    )
    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("asset_segments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(255), default="")
    range_start_ms: Mapped[int] = mapped_column(Integer, default=0)
    range_end_ms: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    shot: Mapped[Shot] = relationship("Shot", back_populates="candidates")


class ShotMediaVersion(Base):
    """镜头的一次生成或处理结果；真实媒体统一存为 Asset。"""

    __tablename__ = "shot_media_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", name="uq_shot_media_version_job_kind"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"media-version-{uuid.uuid4().hex[:12]}"
    )
    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shot_media_versions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(50), default="generated")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    shot: Mapped[Shot] = relationship(
        "Shot", back_populates="media_versions", foreign_keys=[shot_id]
    )
    asset: Mapped["Asset"] = relationship("Asset")  # type: ignore[name-defined]
