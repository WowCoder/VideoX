"""普通用户和运营后台共享的安全任务重放与取消命令。"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspiration import InspirationRun
from app.models.job import Job
from app.models.project import Project
from app.services.quotas import QuotaExceededError, readmit_existing_job_quota
from app.services.task_dispatch import dispatch_owner_task, dispatch_project_task


REPLAYABLE_JOB_TYPES = {
    "素材处理", "AI 初剪生成", "导出", "镜头匹配", "AI 生图分镜",
    "AI 分镜完善", "AI 脚本生成", "分镜图 AI 生视频", "示意图特效视频",
    "AI 配音生成",
}


async def dispatch_replay(
    db: AsyncSession,
    job: Job,
    *,
    project_dispatch=None,
    owner_dispatch=None,
):
    """根据持久化 Payload 真实派发任务。"""
    project_dispatch = project_dispatch or dispatch_project_task
    owner_dispatch = owner_dispatch or dispatch_owner_task

    async def dispatch(task, *args):
        if job.project_id:
            return await project_dispatch(db, job.project_id, task, *args)
        return await owner_dispatch(db, job.owner_id, task, *args)

    if job.type == "素材处理":
        from app.tasks.media_tasks import process_asset
        return await dispatch(process_asset, job.payload["asset_id"], job.id)
    if job.type == "AI 初剪生成":
        from app.tasks.roughcut_tasks import run_rough_cut
        return await dispatch(run_rough_cut, job.id, job.payload["project_id"])
    if job.type == "导出":
        from app.tasks.export_tasks import export_project
        return await dispatch(
            export_project, job.payload["project_id"], job.id,
            job.payload.get("format", "mp4"), job.payload.get("resolution", "1080p"),
            job.payload.get("aspect_ratio"),
        )
    if job.type == "镜头匹配":
        if job.payload.get("shot_ids"):
            from app.tasks.match_tasks import match_script_shots
            return await dispatch(
                match_script_shots, job.payload["script_id"], job.payload["shot_ids"], job.id
            )
        raise HTTPException(status_code=400, detail="旧场景级匹配任务不再支持重放")
    if job.type == "AI 生图分镜":
        from app.tasks.generate_tasks import generate_image_shot
        return await dispatch(generate_image_shot, job.payload["shot_id"], job.id, job.payload.get("prompt", ""))
    if job.type == "AI 分镜完善":
        from app.tasks.script_tasks import complete_shot_descriptions
        return await dispatch(
            complete_shot_descriptions, job.payload["script_id"], job.payload["shot_ids"], job.id
        )
    if job.type == "AI 脚本生成":
        from app.tasks.script_tasks import generate_project_script
        return await dispatch(generate_project_script, job.payload["project_id"], job.id)
    if job.type == "AI 配音生成":
        from app.tasks.voice_tasks import generate_project_voiceover
        return await dispatch(generate_project_voiceover, job.id, job.payload["project_id"])
    if job.type == "分镜图 AI 生视频":
        from app.services.video_queue import wake_video_scheduler

        wake_video_scheduler()
        return None
    if job.type == "示意图特效视频":
        from app.tasks.generate_tasks import generate_effect_shot
        return await dispatch(
            generate_effect_shot, job.payload["shot_id"], job.id,
            job.payload.get("motion_description", ""),
        )
    raise HTTPException(status_code=400, detail=f"{job.type or '该类型'}任务不支持安全重放")


async def retry_job_command(db: AsyncSession, job: Job) -> Job:
    """校验版本和额度后重置并真实派发失败任务。调用方必须先锁定 Job。"""
    if job.status != "FAILED":
        raise HTTPException(status_code=400, detail="只有失败任务可以重试")
    if not job.payload:
        raise HTTPException(status_code=400, detail="该旧任务缺少可重放参数，无法安全重试")
    if job.type not in REPLAYABLE_JOB_TYPES:
        raise HTTPException(status_code=400, detail=f"{job.type or '该类型'}任务不支持安全重放")
    if job.attempts >= job.max_attempts:
        raise HTTPException(status_code=400, detail=f"任务已达到最大重试次数 {job.max_attempts}")

    project = None
    if job.type == "AI 配音生成":
        from app.models.script import Script
        current_revision = (
            await db.execute(select(Script.revision).where(Script.project_id == job.project_id))
        ).scalar_one_or_none()
        base_revision = int((job.payload or {}).get("base_revision", -1))
        if current_revision is None or current_revision != base_revision:
            raise HTTPException(
                status_code=409,
                detail="项目内容已变化，旧配音任务不能直接重试；请从 AI 配音面板重新生成",
            )
        project = await db.get(Project, job.project_id)

    try:
        await readmit_existing_job_quota(db, job, job.owner_id)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=403, detail="当前会员额度不足，暂时无法重试该任务") from exc

    now = datetime.now(timezone.utc)
    job.status = "QUEUED"
    job.progress = 0
    job.stage_index = 0
    job.detail = "任务已重新进入队列"
    job.result = None
    job.result_detail = ""
    job.result_url = None
    job.result_path = None
    job.celery_task_id = None
    job.attempts += 1
    job.started_at = None
    job.finished_at = None
    job.error_code = None
    job.error_category = None
    job.provider_request_id = None
    job.provider_task_id = None
    job.execution_state = "QUEUED" if job.type == "分镜图 AI 生视频" else None
    job.queued_at = now
    job.heartbeat_at = None
    job.submitted_at = None
    job.last_polled_at = None
    job.provider_finished_at = None
    job.next_poll_at = None
    job.submit_attempts = 0
    job.poll_attempts = 0
    if job.stages:
        job.stage = job.stages[0]
    job.updated_at = now
    if project:
        project.status = "processing"
    await db.commit()

    try:
        task = await dispatch_replay(db, job)
        job.celery_task_id = task.id if task is not None else None
        await db.commit()
    except HTTPException:
        job.status = "FAILED"
        job.stage = "重试失败"
        job.detail = "该任务类型不支持安全重试"
        job.error_code = "REPLAY_NOT_SUPPORTED"
        job.error_category = "INVALID_PAYLOAD"
        job.finished_at = datetime.now(timezone.utc)
        if project:
            project.status = "ready"
        await db.commit()
        raise
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"重试任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后再次重试"
        job.error_code = "DISPATCH_FAILED"
        job.error_category = "INTERNAL_ERROR"
        job.finished_at = datetime.now(timezone.utc)
        if project:
            project.status = "ready"
        await db.commit()
    return job


async def cancel_job_command(db: AsyncSession, job: Job, *, actor_label: str) -> Job:
    """真实撤销排队任务或终止正在执行的 Celery 子进程。"""
    pausable_provider_job = (
        job.type == "分镜图 AI 生视频"
        and job.status == "PAUSED"
        and bool(job.provider_task_id)
    )
    if job.status not in {"QUEUED", "RUNNING"} and not pausable_provider_job:
        raise HTTPException(status_code=400, detail="只有排队中或执行中的任务可以取消")
    if job.type == "分镜图 AI 生视频" and job.execution_state in {"SUBMITTING", "PERSISTING"}:
        raise HTTPException(status_code=409, detail="任务正在提交或保存结果，请稍后再取消")
    if job.celery_task_id:
        from app.tasks.celery_app import celery_app
        try:
            celery_app.control.revoke(
                job.celery_task_id,
                # 视频状态机的短任务可能已退出；供应商任务无法通过 SIGTERM
                # 可靠取消，因此只阻止后续轮询/持久化，不强杀 Worker。
                terminate=job.status == "RUNNING" and job.type != "分镜图 AI 生视频",
                signal="SIGTERM",
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"任务取消指令发送失败：{str(exc)[:160]}") from exc
    elif job.type != "分镜图 AI 生视频":
        raise HTTPException(status_code=400, detail="任务缺少 Worker 标识，无法安全取消")

    now = datetime.now(timezone.utc)
    job.status = "CANCELLED"
    job.stage = "已取消"
    job.detail = (
        f"任务已由{actor_label}取消；供应商任务可能仍会完成，但系统将不再查询或写入结果"
        if job.type == "分镜图 AI 生视频" and job.provider_task_id
        else f"任务已由{actor_label}取消"
    )
    job.result = None
    job.result_detail = ""
    job.result_url = None
    job.result_path = None
    job.finished_at = now
    job.updated_at = now
    if job.type == "分镜图 AI 生视频":
        job.execution_state = "CANCELLED"
    run = (
        await db.execute(select(InspirationRun).where(InspirationRun.job_id == job.id))
    ).scalar_one_or_none()
    if run and run.status in {"QUEUED", "RUNNING"}:
        run.status = "CANCELLED"
        run.outcome = "CANCELLED"
        run.error = f"关联任务已由{actor_label}取消"
        run.finished_at = now
    await db.commit()
    if job.type == "分镜图 AI 生视频":
        from app.services.video_queue import refresh_video_batch, wake_video_scheduler

        await refresh_video_batch(db, job.batch_id)
        await db.commit()
        wake_video_scheduler()
    return job
