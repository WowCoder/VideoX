"""非阻塞视频生成状态机：公平调度、提交、单次查询和结果持久化。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


settings = get_settings()


@celery_app.task(
    name="app.tasks.schedule_video_jobs",
    acks_late=True,
    reject_on_worker_lost=True,
)
def schedule_video_jobs() -> int:
    from app.services.video_queue import schedule_video_jobs_once

    return run_async(schedule_video_jobs_once())


@celery_app.task(
    bind=True,
    name="app.tasks.submit_video_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def submit_video_job(self, job_id: str) -> None:
    del self
    run_async(_submit_video_job(job_id))


@celery_app.task(
    bind=True,
    name="app.tasks.poll_video_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_video_job(self, job_id: str) -> None:
    del self
    run_async(_poll_video_job(job_id))


@celery_app.task(
    bind=True,
    name="app.tasks.persist_video_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def persist_video_job(self, job_id: str, result_url: str = "") -> None:
    del self
    run_async(_persist_video_job(job_id, result_url))


async def _mark_failed(job_id: str, detail: str, code: str, category: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.quotas import fail_job
    from app.services.video_queue import refresh_video_batch, wake_video_scheduler

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        completed = await fail_job(
            db,
            job_id,
            detail=detail,
            stage="生成失败",
            error_code=code,
            error_category=category,
            now=now,
        )
        if not completed:
            return
        job = await db.get(Job, job_id)
        if job:
            job.execution_state = "FAILED"
            job.heartbeat_at = now
        await refresh_video_batch(db, job.batch_id if job else None)
        await db.commit()
    wake_video_scheduler()


async def _pause_persistence(job_id: str, detail: str) -> None:
    """保留已付费的供应商任务，等待安全恢复转存，绝不重新提交生成。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.video_queue import refresh_video_batch, wake_video_scheduler

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await db.get(Job, job_id, with_for_update=True)
        if not job or job.status != "RUNNING" or job.execution_state != "PERSISTING":
            return
        job.status = "PAUSED"
        job.execution_state = "PERSIST_PAUSED"
        job.stage = "结果转存待恢复"
        job.detail = f"供应商已完成生成，但结果转存失败：{detail[:350]}；继续任务会读取原结果，不会重新生成"
        job.result_detail = "请确认对象存储和供应商结果地址可用后继续任务"
        job.error_code = "VIDEO_PERSIST_PAUSED"
        job.error_category = "INTERNAL_ERROR"
        job.heartbeat_at = now
        job.next_poll_at = None
        await refresh_video_batch(db, job.batch_id)
        await db.commit()
    wake_video_scheduler()


async def _pause_provider_wait(job_id: str, detail: str) -> None:
    """供应商结果仍可能成功时暂停自动轮询，并保留原 task id。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.video_queue import refresh_video_batch

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await db.get(Job, job_id, with_for_update=True)
        if not job or job.status != "RUNNING" or job.execution_state != "PROVIDER_RUNNING":
            return
        job.status = "PAUSED"
        job.execution_state = "PROVIDER_UNKNOWN"
        job.stage = "供应商任务待确认"
        job.detail = detail[:500]
        job.result_detail = "继续任务将查询原供应商任务，不会重新提交或重复扣费"
        job.error_code = "PROVIDER_RESULT_PENDING_CONFIRMATION"
        job.error_category = "PROVIDER_ERROR"
        job.heartbeat_at = now
        job.next_poll_at = None
        await refresh_video_batch(db, job.batch_id)
        await db.commit()


async def _submit_video_job(job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.ai_provider import submit_video_generation
    from app.tasks.generate_tasks import prepare_video_job_request

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await db.get(Job, job_id, with_for_update=True)
        if not job or job.status != "RUNNING":
            return
        if job.provider_task_id:
            await db.commit()
            poll_video_job.apply_async(
                args=(job.id,), countdown=settings.video_poll_interval_seconds,
                queue=settings.video_queue_name,
            )
            return
        # 只允许调度器刚授予的 DISPATCHING 租约进入付费提交。若 Worker 在
        # 提交中断，Celery 即使重投同一消息也会看到 SUBMITTING 并直接退出，
        # 避免供应商已收单但 task id 尚未落库时重复扣费。
        if job.execution_state != "DISPATCHING":
            return
        job.execution_state = "SUBMITTING"
        job.stage = "提交生成"
        job.progress = max(job.progress, 10)
        job.heartbeat_at = now
        job.submit_attempts += 1
        await db.commit()

    try:
        request = await prepare_video_job_request(job_id)
    except Exception as exc:
        await _mark_failed(
            job_id,
            str(exc),
            "VIDEO_REQUEST_INVALID",
            "INVALID_PAYLOAD",
        )
        return

    try:
        submission = await submit_video_generation(**request["provider_request"])
    except Exception as exc:
        await _mark_failed(
            job_id,
            f"供应商提交结果未能可靠确认：{str(exc)}；为避免重复扣费，未自动重提",
            "PROVIDER_SUBMIT_OUTCOME_UNKNOWN",
            "PROVIDER_ERROR",
        )
        return

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await db.get(Job, job_id, with_for_update=True)
        if not job or job.status != "RUNNING":
            return
        job.provider = str(submission["provider"])
        job.model = str(submission["model"])
        job.provider_task_id = str(submission["task_id"])
        job.provider_request_id = str(submission["task_id"])
        job.submitted_at = now
        job.heartbeat_at = now
        job.execution_state = "PROVIDER_RUNNING"
        job.stage = "等待供应商生成"
        job.progress = 25
        job.next_poll_at = now + timedelta(seconds=settings.video_poll_interval_seconds)
        job.payload = {
            **(job.payload or {}),
            "video_runtime": {
                **request["runtime"],
                "capability": submission["capability"],
                "uses_agnesapi_poll": bool(submission.get("uses_agnesapi_poll")),
            },
        }
        await db.commit()
    poll_video_job.apply_async(
        args=(job_id,), countdown=settings.video_poll_interval_seconds,
        queue=settings.video_queue_name,
    )


async def _poll_video_job(job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.ai_provider import poll_video_generation

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await db.get(Job, job_id)
        if not job or job.status != "RUNNING" or job.execution_state != "PROVIDER_RUNNING":
            return
        runtime = dict((job.payload or {}).get("video_runtime") or {})
        if not job.provider_task_id or not job.provider:
            await _mark_failed(job_id, "供应商任务编号缺失", "PROVIDER_TASK_MISSING", "INTERNAL_ERROR")
            return
        submitted_at = job.submitted_at or job.started_at or now
        if (now - submitted_at).total_seconds() > settings.video_provider_timeout_seconds:
            await _pause_provider_wait(
                job_id,
                "供应商视频任务超过自动等待时限，结果仍不明确，已暂停自动查询",
            )
            return
        provider = job.provider
        task_id = job.provider_task_id
        model = job.model or ""

    try:
        result = await poll_video_generation(
            provider,
            task_id,
            model=model,
            capability=str(runtime.get("capability") or "AI 视频"),
            uses_agnesapi_poll=bool(runtime.get("uses_agnesapi_poll")),
        )
    except Exception as exc:
        # 查询失败不代表生成失败。只要供应商任务 ID 已持久化，就继续按原任务
        # 重试查询，直到统一的 provider timeout，避免瞬时网络故障丢失付费结果。
        delay = settings.video_poll_interval_seconds
        async with async_session_factory() as db:
            job = await db.get(Job, job_id, with_for_update=True)
            if not job or job.status != "RUNNING" or job.execution_state != "PROVIDER_RUNNING":
                return
            job.poll_attempts += 1
            job.last_polled_at = now
            job.heartbeat_at = now
            job.next_poll_at = now + timedelta(seconds=delay)
            job.stage = "等待供应商恢复"
            job.detail = f"本次状态查询失败，将自动重试：{str(exc)[:250]}"
            await db.commit()
        poll_video_job.apply_async(args=(job_id,), countdown=delay, queue=settings.video_queue_name)
        return

    now = datetime.now(timezone.utc)
    if result["state"] == "failed":
        await _mark_failed(
            job_id, str(result.get("error") or "供应商视频任务失败"),
            "PROVIDER_GENERATION_FAILED", "PROVIDER_ERROR",
        )
        return
    if result["state"] == "pending":
        delay = max(1.0, float(result.get("retry_after") or settings.video_poll_interval_seconds))
        async with async_session_factory() as db:
            job = await db.get(Job, job_id, with_for_update=True)
            if not job or job.status != "RUNNING" or job.execution_state != "PROVIDER_RUNNING":
                return
            job.poll_attempts += 1
            job.last_polled_at = now
            job.heartbeat_at = now
            job.next_poll_at = now + timedelta(seconds=delay)
            await db.commit()
        poll_video_job.apply_async(args=(job_id,), countdown=delay, queue=settings.video_queue_name)
        return

    async with async_session_factory() as db:
        job = await db.get(Job, job_id, with_for_update=True)
        if not job or job.status != "RUNNING" or job.execution_state != "PROVIDER_RUNNING":
            return
        job.poll_attempts += 1
        job.last_polled_at = now
        job.provider_finished_at = now
        job.heartbeat_at = now
        job.execution_state = "PERSISTING"
        job.stage = "保存素材"
        job.progress = 75
        job.next_poll_at = None
        await db.commit()
    # 正常完成时在当前短轮询任务内立即转存，临时签名 URL 不进入 Celery
    # Broker/结果后端。若进程此时退出，Beat 会以 provider_task_id 重新查询恢复。
    await _persist_video_job(job_id, str(result.get("result_url") or ""))


async def _persist_video_job(job_id: str, result_url: str = "") -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.ai_provider import poll_video_generation
    from app.services.video_queue import refresh_video_batch, wake_video_scheduler
    from app.tasks.generate_tasks import persist_submitted_video_result

    try:
        async with async_session_factory() as db:
            job = await db.get(Job, job_id)
            if not job or job.status != "RUNNING" or job.execution_state != "PERSISTING":
                return
            runtime = dict((job.payload or {}).get("video_runtime") or {})
            provider = job.provider or ""
            task_id = job.provider_task_id or ""
            model = job.model or ""
        if not result_url:
            result = await poll_video_generation(
                provider,
                task_id,
                model=model,
                capability=str(runtime.get("capability") or "AI 视频"),
                uses_agnesapi_poll=bool(runtime.get("uses_agnesapi_poll")),
            )
            if result.get("state") != "succeeded":
                raise RuntimeError("供应商已完成任务暂时无法重新取得结果地址")
            result_url = str(result.get("result_url") or "")
        await persist_submitted_video_result(job_id, result_url)
    except Exception as exc:
        await _pause_persistence(job_id, str(exc))
        return
    async with async_session_factory() as db:
        job = await db.get(Job, job_id)
        if job:
            await refresh_video_batch(db, job.batch_id)
            await db.commit()
    wake_video_scheduler()
