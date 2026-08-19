"""任务路由：列表/详情/重试/暂停/继续/导出下载。"""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from datetime import datetime, timezone

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.job import Job
from app.schemas.job import JobOut, JobListOut
from app.services.quotas import QuotaExceededError, readmit_existing_job_quota
from app.services.task_dispatch import dispatch_owner_task, dispatch_project_task

router = APIRouter()


def _export_result_path(job: Job) -> str | None:
    if job.result_path:
        return job.result_path
    if job.type != "导出" or job.status != "SUCCEEDED":
        return None
    payload = job.payload or {}
    export_format = str(payload.get("format") or "mp4")
    extension = "mp4" if export_format == "mp4" else "mov"
    return f"exports/{job.project_id}/{job.id}.{extension}"


async def _dispatch_replay(db: AsyncSession, job: Job):
    """根据持久化 payload 真实派发任务；暂停恢复和失败重试共用。"""
    async def dispatch(task, *args):
        if job.project_id:
            return await dispatch_project_task(db, job.project_id, task, *args)
        return await dispatch_owner_task(db, job.owner_id, task, *args)

    if job.type == "素材处理":
        from app.tasks.media_tasks import process_asset
        return await dispatch(process_asset, job.payload["asset_id"], job.id)
    if job.type == "AI 初剪生成":
        from app.tasks.roughcut_tasks import run_rough_cut
        return await dispatch(run_rough_cut, job.id, job.payload["project_id"])
    if job.type == "导出":
        from app.tasks.export_tasks import export_project
        return await dispatch(
            export_project,
            job.payload["project_id"],
            job.id,
            job.payload.get("format", "mp4"),
            job.payload.get("resolution", "1080p"),
            job.payload.get("aspect_ratio"),
        )
    if job.type == "镜头匹配":
        if job.payload.get("shot_ids"):
            from app.tasks.match_tasks import match_script_shots
            return await dispatch(
                match_script_shots,
                job.payload["script_id"],
                job.payload["shot_ids"],
                job.id,
            )
        raise HTTPException(status_code=400, detail="旧场景级匹配任务不再支持重放")
    if job.type == "AI 生图分镜":
        from app.tasks.generate_tasks import generate_image_shot
        return await dispatch(
            generate_image_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("prompt", ""),
        )
    if job.type == "AI 分镜完善":
        from app.tasks.script_tasks import complete_shot_descriptions
        return await dispatch(
            complete_shot_descriptions,
            job.payload["script_id"],
            job.payload["shot_ids"],
            job.id,
        )
    if job.type == "AI 脚本生成":
        from app.tasks.script_tasks import generate_project_script
        return await dispatch(
            generate_project_script,
            job.payload["project_id"],
            job.id,
        )
    if job.type == "分镜图 AI 生视频":
        from app.tasks.generate_tasks import generate_video_shot
        return await dispatch(
            generate_video_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("prompt", ""),
        )
    if job.type == "示意图特效视频":
        from app.tasks.generate_tasks import generate_effect_shot
        return await dispatch(
            generate_effect_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("motion_description", ""),
        )
    raise HTTPException(status_code=400, detail=f"{job.type or '该类型'}任务不支持安全重放")


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
    if job.status != "FAILED":
        raise HTTPException(status_code=400, detail="只有失败任务可以重试")
    if not job.payload:
        raise HTTPException(status_code=400, detail="该旧任务缺少可重放参数，无法安全重试")
    if job.attempts >= job.max_attempts:
        raise HTTPException(status_code=400, detail=f"任务已达到最大重试次数 {job.max_attempts}")

    try:
        await readmit_existing_job_quota(db, job, job.owner_id)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=403, detail="当前会员额度不足，暂时无法重试该任务") from exc

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
    if job.stages:
        job.stage = job.stages[0]
    job.updated_at = datetime.now(timezone.utc)

    await db.commit()

    try:
        task = await _dispatch_replay(db, job)
        job.celery_task_id = task.id
        await db.commit()
    except HTTPException:
        job.status = "FAILED"
        job.stage = "重试失败"
        job.detail = "该任务类型不支持安全重试"
        await db.commit()
        raise
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"重试任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后再次重试"
        await db.commit()

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
    if job.status not in {"QUEUED", "RUNNING"}:
        raise HTTPException(status_code=400, detail="只有排队中或执行中的任务可以取消")
    if not job.celery_task_id:
        raise HTTPException(status_code=400, detail="任务缺少 Worker 标识，无法安全取消")

    from app.tasks.celery_app import celery_app

    try:
        celery_app.control.revoke(
            job.celery_task_id,
            terminate=job.status == "RUNNING",
            signal="SIGTERM",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"任务取消指令发送失败：{str(exc)[:160]}") from exc

    job.status = "CANCELLED"
    job.stage = "已取消"
    job.detail = "任务已由用户取消"
    job.result = None
    job.result_detail = ""
    job.result_url = None
    job.result_path = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
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

    try:
        await readmit_existing_job_quota(db, job, job.owner_id)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=403, detail="当前会员额度不足，暂时无法继续该任务") from exc

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
    await db.commit()
    try:
        task = await _dispatch_replay(db, job)
        job.celery_task_id = task.id
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
    filename = f"{safe_name or 'OpenVMA'}-{job.id}{extension}"
    media_type = "video/mp4" if extension.lower() == ".mp4" else "video/quicktime"
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )
