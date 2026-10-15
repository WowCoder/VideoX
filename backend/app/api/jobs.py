"""任务路由：列表/详情/重试/暂停/继续/导出下载。"""

from collections.abc import Iterator
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update, delete
from datetime import datetime, timezone

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.job import Job, VideoGenerationBatch
from app.models.notification import Notification
from app.models.script import ShotMediaVersion
from app.models.inspiration import InspirationRun
from app.schemas.job import JobOut, JobListOut
from app.services.quotas import QuotaExceededError, readmit_existing_job_quota
from app.services.job_commands import (
    REPLAYABLE_JOB_TYPES,
    cancel_job_command,
    dispatch_replay,
    retry_job_command,
)
from app.services.task_dispatch import dispatch_owner_task, dispatch_project_task

router = APIRouter()


async def _dispatch_replay(db: AsyncSession, job: Job):
    """Compatibility wrapper that keeps dispatch injection available to tests."""
    return await dispatch_replay(
        db,
        job,
        project_dispatch=dispatch_project_task,
        owner_dispatch=dispatch_owner_task,
    )


class JobReviewRequest(BaseModel):
    action: Literal["accept", "reject"]


def _job_can_delete(status: str) -> bool:
    """运行中的记录不能删除；暂停后可删除，产物本身仍保留。"""
    return status not in {"QUEUED", "RUNNING"}


def _export_result_path(job: Job) -> str | None:
    if job.result_path:
        return job.result_path
    if job.type != "导出" or job.status != "SUCCEEDED":
        return None
    payload = job.payload or {}
    export_format = str(payload.get("format") or "mp4")
    extension = "mp4" if export_format == "mp4" else "mov"
    return f"exports/{job.project_id}/{job.id}.{extension}"


@router.get("", response_model=JobListOut)
async def list_jobs(
    project_id: str = Query("", description="按项目筛选"),
    status_filter: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务列表。"""
    query = select(Job).where(Job.owner_id == user.id)

    if project_id:
        query = query.where(Job.project_id == project_id)
    if status_filter:
        query = query.where(Job.status == status_filter)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(desc(Job.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListOut(items=[JobOut.model_validate(j) for j in jobs], total=total)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobOut.model_validate(job)


@router.post("/{job_id}/review", response_model=JobOut)
async def review_job_proposal(
    job_id: str,
    request: JobReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """接受或忽略 AI 分镜描述建议；任务成功本身不会直接覆盖项目。"""
    job = (
        await db.execute(
            select(Job)
            .where(Job.id == job_id, Job.owner_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.type != "AI 分镜完善" or job.status != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="该任务没有可审核的分镜建议")

    payload = dict(job.payload or {})
    proposal = payload.get("review_proposal")
    if not isinstance(proposal, dict) or proposal.get("type") != "shot_description":
        raise HTTPException(status_code=409, detail="该任务没有可审核的分镜建议")
    if proposal.get("status", "pending") != "pending":
        raise HTTPException(status_code=409, detail="这组分镜建议已经处理")

    reviewed_at = datetime.now(timezone.utc).isoformat()
    if request.action == "reject":
        proposal = {**proposal, "status": "rejected", "reviewed_at": reviewed_at}
        job.payload = {**payload, "review_proposal": proposal}
        job.result = "已忽略"
        job.result_detail = "AI 描述建议已忽略，项目内容未改变"
        job.updated_at = datetime.now(timezone.utc)
        if job.project_id:
            await db.execute(
                update(Project).where(Project.id == job.project_id).values(status="ready")
            )
        await db.commit()
        return JobOut.model_validate(job)

    if not job.project_id:
        raise HTTPException(status_code=409, detail="任务未关联项目，无法应用建议")

    from app.services.workspace import load_project_workspace, record_revision

    project = await load_project_workspace(db, job.project_id, user.id, for_update=True)
    shots_by_id = {
        shot.id: shot
        for scene in project.script.units
        for shot in scene.shots
    }
    items = proposal.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=409, detail="AI 没有返回可应用的描述建议")

    changes = []
    conflicts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("shot_id") or "")
        shot = shots_by_id.get(shot_id)
        original = str(item.get("original_description") or "")
        proposed = str(item.get("proposed_description") or "").strip()
        if not shot or not proposed:
            conflicts.append(shot_id or "unknown")
            continue
        if shot.description != original:
            conflicts.append(shot_id)
            continue
        changes.append((shot, proposed))
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail="部分镜头在 AI 生成后已经被编辑，请重新发起 AI 完善",
        )

    for shot, proposed in changes:
        shot.description = proposed
        shot.status = "editing"
        shot.revision += 1
    project.script.revision += 1
    project.composition.revision = project.script.revision
    project.status = "ready"
    proposal = {**proposal, "status": "accepted", "reviewed_at": reviewed_at}
    job.payload = {**payload, "review_proposal": proposal}
    job.result = "已应用"
    job.result_detail = f"已应用 {len(changes)} 条镜头描述建议"
    job.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await record_revision(
        db,
        project,
        user.id,
        "accept_ai_description",
        {"job_id": job.id, "shot_ids": [shot.id for shot, _ in changes]},
    )
    await db.commit()
    return JobOut.model_validate(job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除非运行中的任务记录，不删除已经生成的素材或镜头版本。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not _job_can_delete(job.status):
        raise HTTPException(status_code=409, detail="进行中的任务不能删除，请先暂停任务")
    if (
        job.type == "分镜图 AI 生视频"
        and job.status == "PAUSED"
        and job.provider_task_id
    ):
        raise HTTPException(
            status_code=409,
            detail="供应商任务仍有关联，请先取消任务再删除记录",
        )

    # 显式解除或清理引用，保证不同数据库的外键行为一致；生成产物本身不删除。
    await db.execute(
        update(ShotMediaVersion)
        .where(ShotMediaVersion.job_id == job.id)
        .values(job_id=None)
    )
    await db.execute(
        update(InspirationRun)
        .where(InspirationRun.job_id == job.id)
        .values(job_id=None)
    )
    await db.execute(delete(Notification).where(Notification.job_id == job.id))
    batch_id = job.batch_id
    await db.delete(job)
    await db.flush()
    if batch_id:
        remaining = int(
            (
                await db.execute(
                    select(func.count(Job.id)).where(Job.batch_id == batch_id)
                )
            ).scalar()
            or 0
        )
        batch = await db.get(VideoGenerationBatch, batch_id)
        if batch:
            if remaining == 0:
                await db.delete(batch)
            else:
                from app.services.video_queue import refresh_video_batch

                batch.total_count = remaining
                await refresh_video_batch(db, batch_id)
    await db.commit()


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重试任务。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = await retry_job_command(db, job)
    return JobOut.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """真实撤销排队任务或终止正在执行的 Celery 子进程。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = await cancel_job_command(db, job, actor_label="用户")
    return JobOut.model_validate(job)


@router.post("/{job_id}/pause", response_model=JobOut)
async def pause_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """真实撤销当前执行；恢复时根据 payload 从任务起点重新运行。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in {"QUEUED", "RUNNING"}:
        raise HTTPException(status_code=400, detail="只有排队中或执行中的任务可以暂停")
    if not job.payload:
        raise HTTPException(status_code=400, detail="任务缺少恢复参数，无法安全暂停")
    if job.type == "分镜图 AI 生视频":
        if job.execution_state in {"SUBMITTING", "PERSISTING"}:
            raise HTTPException(status_code=409, detail="任务正在提交或保存结果，请稍后再暂停")
        job.status = "PAUSED"
        job.execution_state = "PAUSED_PROVIDER" if job.provider_task_id else "PAUSED"
        job.stage = "已暂停"
        job.detail = (
            "已暂停状态查询；供应商可能仍在生成，继续后会查询原任务，不会重复提交"
            if job.provider_task_id
            else "任务已从等待队列暂停"
        )
        job.celery_task_id = None
        job.updated_at = datetime.now(timezone.utc)
        from app.services.video_queue import refresh_video_batch, wake_video_scheduler

        await refresh_video_batch(db, job.batch_id)
        await db.commit()
        wake_video_scheduler()
        return JobOut.model_validate(job)
    if not job.celery_task_id:
        raise HTTPException(status_code=400, detail="任务缺少 Worker 标识，无法安全暂停")

    from app.tasks.celery_app import celery_app
    try:
        celery_app.control.revoke(
            job.celery_task_id,
            terminate=job.status == "RUNNING",
            signal="SIGTERM",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"任务暂停指令发送失败：{str(exc)[:160]}") from exc

    job.status = "PAUSED"
    job.stage = "已暂停"
    job.detail = "任务已暂停；继续后将从任务起点重新运行"
    job.celery_task_id = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return JobOut.model_validate(job)


@router.post("/{job_id}/resume", response_model=JobOut)
async def resume_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从持久化 payload 重新派发已暂停任务。"""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != "PAUSED":
        raise HTTPException(status_code=400, detail="只有已暂停任务可以继续")
    if not job.payload:
        raise HTTPException(status_code=400, detail="任务缺少恢复参数，无法安全继续")
    if job.type not in REPLAYABLE_JOB_TYPES:
        raise HTTPException(status_code=400, detail=f"{job.type or '该类型'}任务不支持安全恢复")

    try:
        await readmit_existing_job_quota(db, job, job.owner_id)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=403, detail="当前会员额度不足，暂时无法继续该任务") from exc

    if job.type == "分镜图 AI 生视频" and job.provider_task_id:
        job.status = "RUNNING"
        job.execution_state = "PROVIDER_RUNNING"
        job.stage = "等待供应商生成"
        job.detail = "已恢复查询原供应商任务，不会重复提交"
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()
        from app.config import get_settings
        from app.services.video_queue import refresh_video_batch
        from app.tasks.video_tasks import poll_video_job

        await refresh_video_batch(db, job.batch_id)
        await db.commit()
        poll_video_job.apply_async(
            args=(job.id,),
            queue=get_settings().video_queue_name,
        )
        return JobOut.model_validate(job)

    job.status = "QUEUED"
    job.progress = 0
    job.stage_index = 0
    job.stage = job.stages[0] if job.stages else "等待执行"
    job.detail = "任务已重新进入队列，将从任务起点运行"
    job.result = None
    job.result_detail = ""
    job.result_url = None
    job.result_path = None
    job.updated_at = datetime.now(timezone.utc)
    if job.type == "分镜图 AI 生视频":
        job.execution_state = "QUEUED"
        job.queued_at = job.updated_at
        job.heartbeat_at = None
    await db.commit()
    try:
        task = await _dispatch_replay(db, job)
        job.celery_task_id = task.id if task is not None else None
        await db.commit()
    except HTTPException:
        job.status = "PAUSED"
        job.stage = "恢复失败"
        job.detail = "该任务类型不支持安全恢复"
        await db.commit()
        raise
    except Exception as exc:
        job.status = "PAUSED"
        job.stage = "恢复派发失败"
        job.detail = f"恢复任务派发失败：{str(exc)[:200]}"
        await db.commit()
        raise HTTPException(status_code=503, detail="任务恢复派发失败，请检查 Worker 后重试") from exc
    return JobOut.model_validate(job)


@router.get("/{job_id}/download")
async def download_job_result(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从内部对象路径流式下载已完成导出，避免依赖会过期的签名 URL。"""
    result = await db.execute(
        select(Job, Project)
        .join(Project, Project.id == Job.project_id)
        .where(Job.id == job_id, Job.owner_id == user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    job, project = row
    if job.type != "导出":
        raise HTTPException(status_code=400, detail="该任务没有可下载的导出文件")
    if job.status != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="导出任务尚未成功完成")
    object_name = _export_result_path(job)
    if not object_name:
        raise HTTPException(status_code=404, detail="导出文件路径不存在")

    from app.config import get_settings
    from app.utils.storage import get_minio_client

    settings = get_settings()
    client = get_minio_client()
    try:
        response = client.get_object(settings.minio_bucket, object_name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="导出文件不存在或已失效") from exc

    def chunks() -> Iterator[bytes]:
        try:
            for chunk in response.stream(1024 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    extension = Path(object_name).suffix or ".mp4"
    safe_name = "".join(char if char not in '\\/:*?\"<>|' else "_" for char in project.name)
    filename = f"{safe_name or 'VideoX'}-{job.id}{extension}"
    media_type = "video/mp4" if extension.lower() == ".mp4" else "video/quicktime"
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )
