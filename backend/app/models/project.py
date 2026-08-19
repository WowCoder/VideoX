"""项目聚合根、唯一主成片与版本历史模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """用户拥有的创作项目；脚本和主成片都必须依附于项目。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"project-{uuid.uuid4().hex[:12]}"
    )
    owner_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    initial: Mapped[str] = mapped_column(String(4), default="P")
    type: Mapped[str] = mapped_column(String(50), default="AI 科技 / 产品讲解")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    variant: Mapped[str] = mapped_column(String(50), default="stage")
    cover_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    master_output_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, index=True
    )

    owner: Mapped["User"] = relationship("User", back_populates="projects")  # type: ignore[name-defined]
    script: Mapped["Script"] = relationship(  # type: ignore[name-defined]
        "Script", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    composition: Mapped["ProjectComposition"] = relationship(
        "ProjectComposition", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    revisions: Mapped[list["ProjectRevision"]] = relationship(
        "ProjectRevision",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectRevision.revision",
    )
    asset_links: Mapped[list["ProjectAssetLink"]] = relationship(  # type: ignore[name-defined]
        "ProjectAssetLink", back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="project")  # type: ignore[name-defined]


class ProjectComposition(Base):
    """项目唯一主成片的非叙事结构。

    Scene/Shot 是脚本编排的权威源；这里保存时间线排布、全局图层和工作流引用，
    不能复制一份可独立修改的 Scene/Shot 正文。
    """

    __tablename__ = "project_compositions"

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="16:9")
    resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=25)
    visual_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    global_audio: Mapped[dict] = mapped_column(JSON, default=dict)
    global_overlays: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"duration_ms": 0, "tracks": []}
    )
    visual_layers: Mapped[dict] = mapped_column(JSON, default=lambda: {"items": []})
    global_scopes: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"film": {}, "scenes": {}}
    )
    workflow_graph: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"nodes": [], "edges": []}
    )
    render_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    current_render_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped[Project] = relationship("Project", back_populates="composition")


class ProjectRevision(Base):
    """项目结构化文档的不可变历史版本，不包含媒体二进制。"""

    __tablename__ = "project_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_project_revision_number"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"revision-{uuid.uuid4().hex[:12]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), default="autosave", index=True)
    document_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revision_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="revisions")


class ProjectUndoToken(Base):
    """保存一次可逆删除的结构片段；使用后立即失效。"""

    __tablename__ = "project_undo_tokens"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"undo-{uuid.uuid4().hex[:24]}"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
