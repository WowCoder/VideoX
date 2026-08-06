"""项目模型。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """项目。

    对应详设 4.1 Project：
    id, name, initial, type, description, updatedAt, status,
    assetCount, clipCount, scriptCount, variant, members,
    isNew, sourceScriptId, visualStyle, aspectRatio, aiShotCount
    """
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"project-{uuid.uuid4().hex[:12]}")
    owner_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    initial: Mapped[str] = mapped_column(String(4), default="P")  # 头像首字母
    type: Mapped[str] = mapped_column(String(50), default="AI 科技 / 产品讲解")  # 项目类型
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="等待上传")
    # status 取值: 处理中 / 全部可搜索 / 等待上传 / 脚本编辑中 / 脚本已导入 / AI 初剪生成中 / AI 初剪可编辑
    asset_count: Mapped[int] = mapped_column(Integer, default=0)
    clip_count: Mapped[int] = mapped_column(Integer, default=0)  # 可搜索片段数
    script_count: Mapped[int] = mapped_column(Integer, default=0)
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    # variant: stage/robot/interview/crowd/lights/hall/speaker
    members: Mapped[list] = mapped_column(JSON, default=list)  # ["V","林","陈"]
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── AI 初剪项目专用字段 ──
    source_script_id: Mapped[str] = mapped_column(String(64), ForeignKey("scripts.id"), nullable=True)
    visual_style: Mapped[str] = mapped_column(String(50), nullable=True)  # 风格预设 id
    aspect_ratio: Mapped[str] = mapped_column(String(10), nullable=True)  # 16:9 / 9:16 / 1:1
    ai_shot_count: Mapped[int] = mapped_column(Integer, default=0)  # AI 生成镜头数
    # ── 剪辑时间线 ──
    # 时间线是用户编辑结果，必须持久化到后端；空数组表示项目尚未开始剪辑。
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    timeline_version: Mapped[int] = mapped_column(Integer, default=0)
    timeline_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    owner: Mapped["User"] = relationship("User", back_populates="projects")  # type: ignore
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="project", cascade="all, delete-orphan")  # type: ignore
    scripts: Mapped[list["Script"]] = relationship("Script", back_populates="project", foreign_keys="Script.project_id", cascade="all, delete-orphan")  # type: ignore
    source_script: Mapped["Script"] = relationship("Script", foreign_keys=[source_script_id], post_update=True)  # type: ignore
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="project", cascade="all, delete-orphan")  # type: ignore
    project_members: Mapped[list["ProjectMember"]] = relationship(  # type: ignore
        "ProjectMember", back_populates="project", cascade="all, delete-orphan"
    )
    project_invitations: Mapped[list["ProjectInvitation"]] = relationship(  # type: ignore
        "ProjectInvitation", back_populates="project", cascade="all, delete-orphan"
    )
    media_items: Mapped[list["ProjectMediaItem"]] = relationship(  # type: ignore
        "ProjectMediaItem",
        back_populates="project",
        foreign_keys="ProjectMediaItem.project_id",
        cascade="all, delete-orphan",
    )
