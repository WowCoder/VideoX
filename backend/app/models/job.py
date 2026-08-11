"""异步任务模型。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Index, String, Integer, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """异步任务。

    对应详设 4.6 Job：
    id, projectId, name, type, status, stage, stages[],
    stageIndex, progress, detail, eta, createdAt, logs[],
    result, isSimulated
    """
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "(quota_type IS NULL AND quota_amount = 0) OR "
            "(quota_type IN ('processing_seconds', 'ai_image', 'ai_video', 'export') "
            "AND quota_amount > 0)",
            name="ck_jobs_quota_assignment",
        ),
        Index("ix_jobs_quota_status", "quota_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"job-{uuid.uuid4().hex[:12]}")
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    type: Mapped[str] = mapped_column(String(50), default="")
    # type: 素材处理 / AI 脚本生成 / 镜头匹配 / AI 生图分镜 / 分镜图 AI 生视频 / 示意图特效视频 / AI 初剪生成
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    # status: QUEUED / RUNNING / SUCCEEDED / FAILED / PAUSED / CANCELLED
    stage: Mapped[str] = mapped_column(String(100), default="")  # 当前阶段名
    stages: Mapped[list] = mapped_column(JSON, default=list)  # 所有阶段名列表
    stage_index: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    detail: Mapped[str] = mapped_column(Text, default="")
    eta: Mapped[str] = mapped_column(String(100), default="预计 1-2 分钟")
    logs: Mapped[list] = mapped_column(JSON, default=list)  # 日志列表
    result: Mapped[str] = mapped_column(String(200), nullable=True)
    # result: 打开时间线 / 打开脚本 / 查看结果 / 已进入素材库 / 查看字幕
    result_detail: Mapped[str] = mapped_column(Text, default="")
    result_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    # 内部对象存储路径；result_url 只是短期签名地址，下载时应基于此字段重新签名/流式返回。
    result_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    quota_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quota_amount: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="jobs", foreign_keys=[project_id])  # type: ignore
