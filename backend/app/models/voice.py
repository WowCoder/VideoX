"""AI 配音配置、逻辑台词与生成版本。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VoiceProfile(Base):
    """用户或项目可复用的系统音色配置；首期不创建克隆音色。"""

    __tablename__ = "voice_profiles"
    __table_args__ = (Index("ix_voice_profiles_owner_project", "owner_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"voice-profile-{uuid.uuid4().hex[:12]}")
    owner_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="dashscope")
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="system")
    language: Mapped[str] = mapped_column(String(30), default="Chinese")
    default_instruction: Mapped[str] = mapped_column(Text, default="")
    default_emotion: Mapped[str] = mapped_column(String(40), default="")
    default_speed: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    profile_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class VoiceLine(Base):
    """字幕与 AI 配音共享的统一台词段（cue）。

    名称保留为 VoiceLine 以兼容已经生成的 Take 和 API；业务语义不再是
    “生成配音时临时切出来的一句话”，而是字幕和声音共同引用的时间段。
    """

    __tablename__ = "voice_lines"
    __table_args__ = (
        UniqueConstraint("project_id", "scene_id", "line_index", name="uq_voice_lines_project_scene_index"),
        Index("ix_voice_lines_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"voice-line-{uuid.uuid4().hex[:12]}")
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id: Mapped[str] = mapped_column(String(64), ForeignKey("script_units.id", ondelete="CASCADE"), nullable=False, index=True)
    start_shot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True)
    end_shot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True)
    line_index: Mapped[int] = mapped_column(Integer, default=0)
    source_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_source: Mapped[str] = mapped_column(String(20), default="narration")
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_revision: Mapped[int] = mapped_column(Integer, default=0)
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    target_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    speech_budget_ms: Mapped[int] = mapped_column(Integer, default=0)
    pause_before_ms: Mapped[int] = mapped_column(Integer, default=0)
    pause_after_ms: Mapped[int] = mapped_column(Integer, default=180)
    caption_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_profile_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("voice_profiles.id", ondelete="SET NULL"), nullable=True)
    instruction: Mapped[str] = mapped_column(Text, default="")
    emotion: Mapped[str] = mapped_column(String(40), default="")
    speed_policy: Mapped[str] = mapped_column(String(30), default="timeline_locked")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    timing_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    selected_take_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("voice_takes.id", name="fk_voice_lines_selected_take", ondelete="SET NULL", use_alter=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    takes: Mapped[list["VoiceTake"]] = relationship(
        "VoiceTake",
        back_populates="voice_line",
        cascade="all, delete-orphan",
        foreign_keys="VoiceTake.voice_line_id",
        order_by="VoiceTake.created_at.desc()",
    )


class VoiceTake(Base):
    """一次真实 TTS 调用或缓存复用产生的音频版本。"""

    __tablename__ = "voice_takes"
    __table_args__ = (
        Index("ix_voice_takes_line_created", "voice_line_id", "created_at"),
        Index("ix_voice_takes_request_hash", "request_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"voice-take-{uuid.uuid4().hex[:12]}")
    voice_line_id: Mapped[str] = mapped_column(String(64), ForeignKey("voice_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_characters: Mapped[int] = mapped_column(Integer, default=0)
    billed_characters: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_stretch_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    instruction: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    voice_line: Mapped[VoiceLine] = relationship(
        "VoiceLine", back_populates="takes", foreign_keys=[voice_line_id]
    )
