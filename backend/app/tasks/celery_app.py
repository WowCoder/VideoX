"""Celery 应用配置。"""

from celery import Celery
from celery.signals import heartbeat_sent, worker_ready
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
        "app.tasks.video_tasks",
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
    task_routes={
        "app.tasks.schedule_video_jobs": {"queue": settings.control_queue_name},
        "app.tasks.write_system_heartbeat": {"queue": settings.control_queue_name},
        "app.tasks.collect_system_metrics": {"queue": settings.control_queue_name},
        "app.tasks.fail_stale_jobs": {"queue": settings.control_queue_name},
        "app.tasks.expire_due_subscriptions": {"queue": settings.control_queue_name},
        "app.tasks.grant_due_subscription_credits": {"queue": settings.control_queue_name},
        "app.tasks.scan_due_inspiration_tasks": {"queue": settings.control_queue_name},
        "app.tasks.submit_video_job": {"queue": settings.video_queue_name},
        "app.tasks.poll_video_job": {"queue": settings.video_queue_name},
        "app.tasks.persist_video_job": {"queue": settings.video_queue_name},
        "app.tasks.process_asset": {"queue": settings.media_queue_name},
        "app.tasks.retry_asset_processing": {"queue": settings.media_queue_name},
        "app.tasks.export_project": {"queue": settings.export_queue_name},
        "app.tasks.generate_image_shot": {"queue": settings.short_ai_queue_name},
        "app.tasks.generate_effect_shot": {"queue": settings.short_ai_queue_name},
        "app.tasks.generate_project_script": {"queue": settings.short_ai_queue_name},
        "app.tasks.complete_shot_descriptions": {"queue": settings.short_ai_queue_name},
        "app.tasks.match_script_shots": {"queue": settings.short_ai_queue_name},
        "app.tasks.run_inspiration_task": {"queue": settings.short_ai_queue_name},
        "app.tasks.generate_project_voiceover": {"queue": settings.short_ai_queue_name},
    },
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
        "grant-due-subscription-credits-hourly": {
            "task": "app.tasks.grant_due_subscription_credits",
            "schedule": 3600.0,
        },
        "scan-due-inspiration-tasks-every-minute": {
            "task": "app.tasks.scan_due_inspiration_tasks",
            "schedule": 60.0,
        },
        "write-system-heartbeat-every-thirty-seconds": {
            "task": "app.tasks.write_system_heartbeat",
            "schedule": 30.0,
        },
        "collect-system-metrics-hourly": {
            "task": "app.tasks.collect_system_metrics",
            "schedule": 3600.0,
        },
        "schedule-video-jobs": {
            "task": "app.tasks.schedule_video_jobs",
            "schedule": settings.video_dispatch_interval_seconds,
        },
    },
)


def _write_worker_heartbeat(sender=None, **_kwargs) -> None:
    """Celery Worker 自身心跳；失败不阻断任务进程。"""
    try:
        import redis

        hostname = str(getattr(sender, "hostname", None) or getattr(sender, "consumer", None) or "worker")
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.setex(f"openvma:heartbeat:worker:{hostname}", 90, datetime.now(timezone.utc).isoformat())
        client.close()
    except Exception:
        return


worker_ready.connect(_write_worker_heartbeat, weak=False)
heartbeat_sent.connect(_write_worker_heartbeat, weak=False)


@celery_app.task(name="app.tasks.write_system_heartbeat")
def write_system_heartbeat() -> None:
    """由 Beat 周期派发、Worker 执行；证明完整调度链路可用。"""
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.setex("openvma:heartbeat:beat-dispatch", 90, datetime.now(timezone.utc).isoformat())
        client.close()
    except Exception:
        return


@celery_app.task(name="app.tasks.collect_system_metrics")
def collect_system_metrics_task() -> None:
    """每小时保存一次低频服务器资源快照。"""
    from app.database import async_session_factory
    from app.services.system_metrics import collect_and_store_system_metrics
    from app.tasks.async_runner import run_async

    async def _collect() -> None:
        async with async_session_factory() as session:
            await collect_and_store_system_metrics(session, source="scheduled")
            await session.commit()

    run_async(_collect())


@celery_app.task(name="app.tasks.fail_stale_jobs")
def fail_stale_jobs():
    """将长时间无更新的排队/运行任务标记为真实失败，避免永久卡死。"""
    from app.database import async_session_factory
    from app.models.inspiration import InspirationRun
    from app.models.job import Job
    from app.services.quotas import fail_job
    from app.tasks.async_runner import run_async
    from sqlalchemy import select, update

    async def _fail_stale():
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            queued_ids = (
                await session.execute(
                    select(Job.id).where(
                        Job.status == "QUEUED",
                        Job.type != "分镜图 AI 生视频",
                        Job.updated_at < now - timedelta(minutes=30),
                    )
                )
            ).scalars().all()
            for job_id in queued_ids:
                await fail_job(
                    session,
                    job_id,
                    stage="排队超时",
                    detail="任务长时间未被 Worker 接收",
                    error_code="QUEUE_TIMEOUT",
                    error_category="WORKER_LOST",
                    now=now,
                )
            running_ids = (
                await session.execute(
                    select(Job.id).where(
                        Job.status == "RUNNING",
                        Job.type != "分镜图 AI 生视频",
                        Job.updated_at < now - timedelta(minutes=75),
                    )
                )
            ).scalars().all()
            for job_id in running_ids:
                await fail_job(
                    session,
                    job_id,
                    stage="执行超时",
                    detail="任务长时间没有心跳，Worker 可能已退出",
                    error_code="EXECUTION_TIMEOUT",
                    error_category="WORKER_LOST",
                    now=now,
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
