"""视频生成批次背压、公平调度与批次进度汇总。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.job import Job, VideoGenerationBatch


settings = get_settings()
logger = logging.getLogger(__name__)
VIDEO_JOB_TYPE = "分镜图 AI 生视频"
VIDEO_INFLIGHT_STATES = {"DISPATCHING", "SUBMITTING", "PROVIDER_RUNNING", "PERSISTING"}


def round_robin_video_candidates(candidates: list[Job]) -> list[Job]:
    """按查询得到的批次优先级交错任务，单批次时保持原始顺序。"""
    jobs_by_batch: dict[str, list[Job]] = {}
    for candidate in candidates:
        jobs_by_batch.setdefault(candidate.batch_id or candidate.id, []).append(candidate)
    return [
        bucket[index]
        for index in range(max((len(bucket) for bucket in jobs_by_batch.values()), default=0))
        for bucket in jobs_by_batch.values()
        if index < len(bucket)
    ]


async def ensure_video_queue_capacity(
    db: AsyncSession,
    owner_id: str,
    project_id: str,
    requested: int,
) -> None:
    """在事务级全局锁下检查批次、用户、项目和全站排队容量。"""
    if requested < 1:
        raise ValueError("视频生成批次不能为空")
    if requested > settings.video_batch_max_shots:
        raise ValueError(
            f"单次最多生成 {settings.video_batch_max_shots} 个镜头，请缩小作用范围"
        )
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": 867530932},
        )
    active = ("QUEUED", "RUNNING", "PAUSED")
    global_count = int(
        (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.type == VIDEO_JOB_TYPE, Job.status.in_(active)
                )
            )
        ).scalar()
        or 0
    )
    user_count = int(
        (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.type == VIDEO_JOB_TYPE,
                    Job.owner_id == owner_id,
                    Job.status.in_(active),
                )
            )
        ).scalar()
        or 0
    )
    project_count = int(
        (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.type == VIDEO_JOB_TYPE,
                    Job.project_id == project_id,
                    Job.status.in_(active),
                )
            )
        ).scalar()
        or 0
    )
    if global_count + requested > settings.video_queue_max_global:
        raise ValueError("全站视频队列已满，请等待部分任务完成后再提交")
    if user_count + requested > settings.video_queue_max_per_user:
        remaining = max(0, settings.video_queue_max_per_user - user_count)
        raise ValueError(f"当前账号视频队列容量不足，本次最多还能加入 {remaining} 个镜头")
    if project_count + requested > settings.video_queue_max_per_project:
        remaining = max(0, settings.video_queue_max_per_project - project_count)
        raise ValueError(f"当前项目视频队列容量不足，本次最多还能加入 {remaining} 个镜头")


async def refresh_video_batch(db: AsyncSession, batch_id: str | None) -> None:
    if not batch_id:
        return
    batch = await db.get(VideoGenerationBatch, batch_id)
    if batch is None:
        return
    rows = (
        await db.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.batch_id == batch_id)
            .group_by(Job.status)
        )
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    batch.succeeded_count = counts.get("SUCCEEDED", 0)
    batch.failed_count = counts.get("FAILED", 0)
    batch.cancelled_count = counts.get("CANCELLED", 0)
    finished = batch.succeeded_count + batch.failed_count + batch.cancelled_count
    now = datetime.now(timezone.utc)
    batch.updated_at = now
    if finished >= batch.total_count:
        if batch.cancelled_count == batch.total_count:
            batch.status = "CANCELLED"
        elif batch.failed_count or batch.cancelled_count:
            batch.status = "FAILED"
        else:
            batch.status = "SUCCEEDED"
        batch.finished_at = now
    elif counts.get("RUNNING", 0):
        batch.status = "RUNNING"
        batch.finished_at = None
    elif counts.get("PAUSED", 0) and not counts.get("QUEUED", 0):
        batch.status = "PAUSED"
        batch.finished_at = None
    else:
        batch.status = "QUEUED"
        batch.finished_at = None


async def _try_scheduler_lock(db: AsyncSession) -> bool:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    return bool(
        (
            await db.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": 867530933},
            )
        ).scalar()
    )


async def _recover_abandoned_dispatches(db: AsyncSession, now: datetime) -> None:
    cutoff = now - timedelta(seconds=settings.job_heartbeat_timeout_seconds)
    jobs = (
        await db.execute(
            select(Job)
            .where(
                Job.type == VIDEO_JOB_TYPE,
                Job.status == "RUNNING",
                Job.execution_state.in_(["DISPATCHING", "SUBMITTING"]),
                Job.provider_task_id.is_(None),
                or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff),
            )
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    for job in jobs:
        if job.execution_state == "SUBMITTING":
            # 供应商可能已收到请求但 Worker 来不及保存 task_id。自动重提可能重复付费，
            # 因此转人工可重试失败，而不是静默再次提交。
            job.status = "FAILED"
            job.execution_state = "FAILED"
            job.stage = "提交结果未知"
            job.detail = "Worker 在保存供应商任务编号前中断；为避免重复扣费，未自动重试"
            job.error_code = "PROVIDER_SUBMIT_OUTCOME_UNKNOWN"
            job.error_category = "WORKER_LOST"
            job.finished_at = now
            await refresh_video_batch(db, job.batch_id)
        else:
            job.status = "QUEUED"
            job.execution_state = "QUEUED"
            job.stage = "等待调度"
            job.detail = "调度租约已恢复，任务将重新进入公平队列"
            job.celery_task_id = None
            job.started_at = None
            job.heartbeat_at = now

    # 已拿到供应商 task id 的任务可以安全恢复：重新查询或重新转存都不会
    # 再次调用生成接口。Beat 会兜底修复 Worker 在短任务之间退出的情况。
    recoverable = (
        await db.execute(
            select(Job)
            .where(
                Job.type == VIDEO_JOB_TYPE,
                Job.status == "RUNNING",
                Job.provider_task_id.is_not(None),
                Job.execution_state.in_(["PROVIDER_RUNNING", "PERSISTING"]),
                or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff),
            )
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    from app.tasks.video_tasks import persist_video_job, poll_video_job

    for job in recoverable:
        task = (
            persist_video_job.apply_async(args=(job.id,), queue=settings.video_queue_name)
            if job.execution_state == "PERSISTING"
            else poll_video_job.apply_async(args=(job.id,), queue=settings.video_queue_name)
        )
        job.celery_task_id = task.id
        job.heartbeat_at = now
        job.detail = "Worker 租约已恢复，正在继续原供应商任务"


async def _inflight_counts(db: AsyncSession) -> tuple[int, dict[str, int], dict[str, int]]:
    rows = (
        await db.execute(
            select(Job.owner_id, Job.project_id, func.count(Job.id))
            .where(
                Job.type == VIDEO_JOB_TYPE,
                or_(
                    and_(
                        Job.status == "RUNNING",
                        Job.execution_state.in_(VIDEO_INFLIGHT_STATES),
                    ),
                    and_(
                        Job.status == "PAUSED",
                        Job.execution_state.in_(["PAUSED_PROVIDER", "PROVIDER_UNKNOWN"]),
                        Job.provider_task_id.is_not(None),
                    ),
                ),
            )
            .group_by(Job.owner_id, Job.project_id)
        )
    ).all()
    by_user: dict[str, int] = defaultdict(int)
    by_project: dict[str, int] = defaultdict(int)
    total = 0
    for owner_id, project_id, count in rows:
        amount = int(count)
        total += amount
        by_user[str(owner_id)] += amount
        if project_id:
            by_project[str(project_id)] += amount
    return total, by_user, by_project


async def schedule_video_jobs_once() -> int:
    """在全局/用户/项目上限内按批次最近派发时间轮询放行镜头任务。"""
    from app.database import async_session_factory
    from app.tasks.video_tasks import submit_video_job

    dispatched = 0
    async with async_session_factory() as db:
        if not await _try_scheduler_lock(db):
            return 0
        now = datetime.now(timezone.utc)
        await _recover_abandoned_dispatches(db, now)
        await db.flush()
        total, by_user, by_project = await _inflight_counts(db)
        available = max(0, settings.video_inflight_max_global - total)
        if not available:
            await db.commit()
            return 0

        candidates = (
            await db.execute(
                select(Job)
                .outerjoin(VideoGenerationBatch, VideoGenerationBatch.id == Job.batch_id)
                .where(
                    Job.type == VIDEO_JOB_TYPE,
                    Job.status == "QUEUED",
                    Job.execution_state == "QUEUED",
                )
                .options(selectinload(Job.video_batch))
                .order_by(
                    VideoGenerationBatch.last_dispatched_at.asc().nullsfirst(),
                    Job.queued_at.asc().nullsfirst(),
                    Job.created_at.asc(),
                )
                .limit(min(1000, settings.video_queue_max_global))
                .with_for_update(skip_locked=True, of=Job)
            )
        ).scalars().all()

        # SQL 排序先确定最久未派发的批次；再把各批次内部任务交错展开，避免
        # 单个大项目一次拿走全部全局名额。若只有一个批次，它仍可用满名额。
        round_robin_candidates = round_robin_video_candidates(candidates)

        for job in round_robin_candidates:
            if dispatched >= available:
                break
            queued_at = job.queued_at or job.created_at or now
            queue_age = max(0, int((now - queued_at).total_seconds()))
            if queue_age >= settings.job_queue_max_age_seconds:
                job.status = "PAUSED"
                job.execution_state = "PAUSED"
                job.stage = "排队已暂停"
                job.detail = "任务排队时间过长，已暂停；确认项目仍需要该镜头后可继续"
                await refresh_video_batch(db, job.batch_id)
                continue
            if queue_age >= settings.job_queue_warning_seconds:
                job.stage = "排队时间较长"
                job.detail = "任务仍在公平队列中等待，不会因为排队超时而自动失败"
            if by_user[job.owner_id] >= settings.video_inflight_max_per_user:
                continue
            if job.project_id and by_project[job.project_id] >= settings.video_inflight_max_per_project:
                continue

            job.status = "RUNNING"
            job.execution_state = "DISPATCHING"
            job.stage = "准备提交"
            job.detail = "已获得视频生成执行名额"
            job.started_at = job.started_at or now
            job.heartbeat_at = now
            if job.video_batch:
                job.video_batch.status = "RUNNING"
                job.video_batch.last_dispatched_at = now
                job.video_batch.updated_at = now
            await db.flush()
            try:
                task = submit_video_job.apply_async(
                    args=(job.id,),
                    countdown=1,
                    queue=settings.video_queue_name,
                )
            except Exception:
                job.status = "QUEUED"
                job.execution_state = "QUEUED"
                job.stage = "等待调度"
                job.detail = "Worker 派发失败，任务将由调度器自动重试"
                job.started_at = None
                continue
            job.celery_task_id = task.id
            dispatched += 1
            by_user[job.owner_id] += 1
            if job.project_id:
                by_project[job.project_id] += 1

        await db.commit()
    return dispatched


def wake_video_scheduler() -> bool:
    """有新任务或名额释放时立即唤醒调度器；Beat 仍负责兜底。"""
    from app.tasks.video_tasks import schedule_video_jobs

    try:
        schedule_video_jobs.apply_async(queue=settings.control_queue_name)
    except Exception as exc:
        # Job 已持久化后 Redis 短暂不可用不应让 API 返回“提交失败”，否则
        # 客户端重试只会撞到幂等冲突。Beat 恢复后仍会自动扫描队列。
        logger.warning("Unable to wake video scheduler; Celery Beat will retry: %s", exc)
        return False
    return True
