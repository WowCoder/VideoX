"""脚本、分镜单元、镜头、候选模型。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Script(Base):
    """脚本。

    对应详设 4.3 Script：
    id, projectId, title, summary, status, updatedAt, duration,
    unitCount, matchedCount, progress, variant, format,
    visualConfig, needsInitialSave
    """
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"script-{uuid.uuid4().hex[:12]}")
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="编辑中")
    # status: 编辑中 / 待匹配 / 待确认 / 已完成 / 初剪生成中 / 初剪可编辑
    duration: Mapped[str] = mapped_column(String(10), default="00:00")  # "MM:SS"
    unit_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    format: Mapped[str] = mapped_column(String(20), default="横屏 16:9")  # 横屏16:9/竖屏9:16/方形1:1
    # ── 视觉一致性配置 ──
    visual_config: Mapped[dict] = mapped_column(JSON, default=lambda: {
        "stylePreset": "brand-tech",
        "aspectRatio": "16:9",
        "palette": "冷灰蓝",
        "cameraRhythm": "稳定推进",
        "consistencyEnabled": True,
        "generationPolicy": "优先使用项目素材，缺失镜头由 AI 补齐",
        "references": {"characters": [], "objects": [], "spaces": []},
    })
    needs_initial_save: Mapped[bool] = mapped_column(Boolean, default=True)
    # ── 来源 ──
    source_type: Mapped[str] = mapped_column(String(20), default="blank")
    # source_type: blank / paste / spreadsheet / ai
    is_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parent_script_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship("Project", back_populates="scripts", foreign_keys=[project_id])  # type: ignore
    units: Mapped[list["ScriptUnit"]] = relationship("ScriptUnit", back_populates="script", cascade="all, delete-orphan", order_by="ScriptUnit.index")


class ScriptUnit(Base):
    """脚本单元（分镜段落）。

    对应详设 4.4 ScriptUnit：
    id, index, outline, text, intent, status,
    selectedClipId, duration, notes, candidates[], shots[]
    """
    __tablename__ = "script_units"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"unit-{uuid.uuid4().hex[:12]}")
    script_id: Mapped[str] = mapped_column(String(64), ForeignKey("scripts.id"), nullable=False, index=True)
    source_unit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("script_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    index: Mapped[int] = mapped_column(Integer, default=0)  # 序号
    outline: Mapped[str] = mapped_column(String(200), default="")  # 大纲（截取前 16 字）
    text: Mapped[str] = mapped_column(Text, default="")  # 台词/旁白
    intent: Mapped[str] = mapped_column(Text, default="")  # 画面意图
    status: Mapped[str] = mapped_column(String(50), default="待编辑")
    # status: 已选择 / 有候选 / 待确认 / 待编辑
    selected_clip_id: Mapped[str] = mapped_column(String(64), ForeignKey("clips.id"), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=8)  # 秒
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    script: Mapped["Script"] = relationship("Script", back_populates="units")
    shots: Mapped[list["Shot"]] = relationship("Shot", back_populates="unit", cascade="all, delete-orphan", order_by="Shot.index")
    # 候选列表存在 JSON 中（兼容 MVP2 数据结构）
    candidates: Mapped[list] = mapped_column(JSON, default=list)


class Shot(Base):
    """分镜（单个镜头）。

    对应详设 4.5 Shot：
    id, description, status, selectedClipId, visualMode,
    duration, notes, candidates[]
    """
    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"shot-{uuid.uuid4().hex[:12]}")
    unit_id: Mapped[str] = mapped_column(String(64), ForeignKey("script_units.id"), nullable=False, index=True)
    source_shot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    index: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")  # 分镜描述
    status: Mapped[str] = mapped_column(String(50), default="待编辑")
    # status: 已选择 / 待编辑 / 待确认
    selected_clip_id: Mapped[str] = mapped_column(String(64), ForeignKey("clips.id"), nullable=True)
    visual_mode: Mapped[str] = mapped_column(String(20), nullable=True)
    # visual_mode: recommend / image / video / sketch
    duration: Mapped[int] = mapped_column(Integer, default=8)  # 秒
    notes: Mapped[str] = mapped_column(Text, default="")
    # ── AI 生成结果 ──
    generated_image_path: Mapped[str] = mapped_column(String(500), nullable=True)  # AI 生图路径
    generated_video_path: Mapped[str] = mapped_column(String(500), nullable=True)  # AI 生视频路径
    generated_effect_video_path: Mapped[str] = mapped_column(String(500), nullable=True)  # 草图特效视频路径
    # ── 示意特效 Canvas 数据 ──
    sketch_data: Mapped[str] = mapped_column(Text, nullable=True)  # JSON 序列化的 canvas 数据
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    unit: Mapped["ScriptUnit"] = relationship("ScriptUnit", back_populates="shots")
    # 候选列表存在 JSON 中
    candidates: Mapped[list] = mapped_column(JSON, default=list)


class Candidate(Base):
    """候选镜头（素材匹配结果）。

    对应详设 4.6 Candidate：
    id, title, source, range, score, reason, variant, lowConfidence
    """
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"cand-{uuid.uuid4().hex[:12]}")
    shot_id: Mapped[str] = mapped_column(String(64), ForeignKey("shots.id"), nullable=True, index=True)
    unit_id: Mapped[str] = mapped_column(String(64), ForeignKey("script_units.id"), nullable=True, index=True)
    clip_id: Mapped[str] = mapped_column(String(64), ForeignKey("clips.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(255), default="")  # 源素材文件名
    range_start: Mapped[str] = mapped_column(String(20), default="")  # "01:15"
    range_end: Mapped[str] = mapped_column(String(20), default="")  # "01:22"
    score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    reason: Mapped[str] = mapped_column(Text, default="")  # 匹配原因
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)  # score < 70
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
