"""灵感岛正式任务、来源、运行、快照与结果模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InspirationTask(Base):
    __tablename__ = "inspiration_tasks"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"inspiration-task-{uuid.uuid4().hex[:12]}"
    )
    owner_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    topic_brief: Mapped[str] = mapped_column(Text, default="")
    topic_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"type": "daily", "time": "09:00", "weekday": 1, "time_zone": "Asia/Shanghai"},
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    sources: Mapped[list["InspirationSource"]] = relationship(
        "InspirationSource", back_populates="task", cascade="all, delete-orphan"
    )
    runs: Mapped[list["InspirationRun"]] = relationship(
        "InspirationRun", back_populates="task", cascade="all, delete-orphan"
    )

    @property
    def output_format(self) -> str:
        if self.task_type == "link-update":
            return "更新内容总结 + 原文外链"
        return "格式化选题 + 参考外链"


class InspirationSource(Base):
    __tablename__ = "inspiration_sources"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"inspiration-source-{uuid.uuid4().hex[:12]}"
    )
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("inspiration_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), default="web")
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    fetch_config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    task: Mapped[InspirationTask] = relationship("InspirationTask", back_populates="sources")


class InspirationRun(Base):
    __tablename__ = "inspiration_runs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"inspiration-run-{uuid.uuid4().hex[:12]}"
    )
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("inspiration_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    task: Mapped[InspirationTask] = relationship("InspirationTask", back_populates="runs")
    results: Mapped[list["InspirationResult"]] = relationship(
        "InspirationResult", back_populates="run", cascade="all, delete-orphan"
    )


class InspirationSourceSnapshot(Base):
    __tablename__ = "inspiration_source_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "run_id", name="uq_inspiration_source_run"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"source-snapshot-{uuid.uuid4().hex[:12]}"
    )
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("inspiration_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("inspiration_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, default="")
    cleaned_content: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InspirationResult(Base):
    __tablename__ = "inspiration_results"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"inspiration-result-{uuid.uuid4().hex[:12]}"
    )
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("inspiration_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped[InspirationRun] = relationship("InspirationRun", back_populates="results")
