"""Celery 应用配置。"""

from celery import Celery
from datetime import datetime, timedelta, timezone

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "openvma",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.media_tasks",
        "app.tasks.match_tasks",
        "app.tasks.generate_tasks",
        "app.tasks.script_tasks",
        "app.tasks.roughcut_tasks",
        "app.tasks.export_tasks",
        "app.tasks.inspiration_tasks",
        "app.tasks.subscription_tasks",
        "app.tasks.voice_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.celery_task_default_queue,
    task_default_exchange=settings.celery_task_default_queue,
    task_default_routing_key=settings.celery_task_default_queue,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 单任务最大 1 小时
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
    task_default_priority=9,
    task_inherit_parent_priority=True,
    broker_transport_options={
        "priority_steps": [0, 4, 9],
        "sep": ":",
        "queue_order_strategy": "priority",
    },
    beat_schedule={
        "fail-stale-jobs-every-five-minutes": {
            "task": "app.tasks.fail_stale_jobs",
            "schedule": 300.0,
        },
        "expire-memberships-hourly": {
            "task": "app.tasks.expire_due_subscriptions",
            "schedule": 3600.0,
        },
        "scan-due-inspiration-tasks-every-minute": {
            "task": "app.tasks.scan_due_inspiration_tasks",
            "schedule": 60.0,
        },
    },
)


@celery_app.task(name="app.tasks.fail_stale_jobs")
def fail_stale_jobs():
    """将长时间无更新的排队/运行任务标记为真实失败，避免永久卡死。"""
    from app.database import async_session_factory
    from app.models.inspiration import InspirationRun
    from app.models.job import Job
    from app.tasks.async_runner import run_async
    from sqlalchemy import select, update

    async def _fail_stale():
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            await session.execute(
                update(Job)
                .where(
                    Job.status == "QUEUED",
                    Job.updated_at < now - timedelta(minutes=30),
                )
                .values(
                    status="FAILED",
                    stage="排队超时",
                    detail="任务长时间未被 Worker 接收",
                    result=None,
                    result_detail="请确认 Worker 正常运行后重试任务",
                    result_url=None,
                    updated_at=now,
                )
            )
            await session.execute(
                update(Job)
                .where(
                    Job.status == "RUNNING",
                    Job.updated_at < now - timedelta(minutes=75),
                )
                .values(
                    status="FAILED",
                    stage="执行超时",
                    detail="任务长时间没有心跳，Worker 可能已退出",
                    result=None,
                    result_detail="请检查 Worker 日志后重试任务",
                    result_url=None,
                    updated_at=now,
                )
            )
            # Job 与领域 Run 必须进入同一终态，避免灵感任务被永久视为正在执行。
            await session.execute(
                update(InspirationRun)
                .where(
                    InspirationRun.status.in_(["QUEUED", "RUNNING"]),
                    InspirationRun.job_id.in_(
                        select(Job.id).where(Job.status == "FAILED")
                    ),
                )
                .values(
                    status="FAILED",
                    outcome="FAILED",
                    error="关联后台任务已超时或失败",
                    finished_at=now,
                )
            )
            await session.commit()

    run_async(_fail_stale())


@celery_app.task(bind=True, name="app.tasks.update_job_progress")
def update_job_progress(self, job_id: str, progress: int, stage: str = "", stage_index: int = None, detail: str = ""):
    """更新任务进度（供 worker 调用）。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from app.tasks.async_runner import run_async
    from sqlalchemy import update

    async def _update():
        async with async_session_factory() as session:
            values = {"progress": progress, "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}
            if stage:
                values["stage"] = stage
            if stage_index is not None:
                values["stage_index"] = stage_index
            if detail:
                values["detail"] = detail
            await session.execute(update(Job).where(Job.id == job_id).values(**values))
            await session.commit()

    run_async(_update())
