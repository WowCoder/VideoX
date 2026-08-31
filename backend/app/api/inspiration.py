"""灵感岛正式任务、运行和结果 API。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.inspiration import InspirationRun, InspirationSource, InspirationTask
from app.models.job import Job
from app.models.user import User
from app.schemas.inspiration import (
    InspirationRunListOut,
    InspirationRunOut,
    InspirationSourceCreate,
    InspirationTaskCreate,
    InspirationTaskListOut,
    InspirationTaskOut,
    InspirationTaskUpdate,
)
from app.services.inspiration_schedule import next_inspiration_run
from app.services.task_dispatch import dispatch_owner_task


router = APIRouter()


def _task_out(task: InspirationTask) -> InspirationTaskOut:
    result = InspirationTaskOut.model_validate(task)
    return result.model_copy(update={"sources": [source for source in result.sources if source.enabled]})


def _validate_sources(sources: list[InspirationSourceCreate]) -> None:
    urls: set[str] = set()
    for source in sources:
        url = str(source.url)
        if not url.lower().startswith("https://"):
            raise HTTPException(status_code=422, detail="灵感来源只允许 HTTPS 地址")
        if url in urls:
            raise HTTPException(status_code=422, detail="同一任务不能重复添加相同来源")
        urls.add(url)


def _sync_sources(task: InspirationTask, sources: list[InspirationSourceCreate]) -> None:
    """替换当前输入，但停用移除项以保留旧快照和运行证据。"""
    requested = {str(source.url): source for source in sources}
    current = {source.url: source for source in task.sources}
    for url, source in current.items():
        source.enabled = url in requested
    for url, request in requested.items():
        if url in current:
            current[url].enabled = True
            current[url].source_type = request.source_type
            current[url].fetch_config = request.fetch_config
        else:
            task.sources.append(
                InspirationSource(
                    source_type=request.source_type,
                    url=url,
                    fetch_config=request.fetch_config,
                    enabled=True,
                )
            )


@router.get("/tasks", response_model=InspirationTaskListOut)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(InspirationTask).where(
                InspirationTask.owner_id == user.id
            )
        )
    ).scalar() or 0
    rows = (
        await db.execute(
            select(InspirationTask)
            .where(InspirationTask.owner_id == user.id)
            .options(selectinload(InspirationTask.sources))
            .order_by(InspirationTask.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().unique().all()
    return {"items": [_task_out(item) for item in rows], "total": int(total)}


@router.post("/tasks", response_model=InspirationTaskOut, status_code=201)
async def create_task(
    request: InspirationTaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_sources(request.sources)
    now = datetime.now(timezone.utc)
    task = InspirationTask(
        owner_id=user.id,
        name=request.name,
        task_type=request.task_type,
        topic_brief=request.topic_brief,
        topic_count=request.topic_count,
        discovery_config=request.discovery_config.model_dump(mode="json"),
        schedule=request.schedule.model_dump(mode="json"),
        enabled=request.enabled,
        next_run_at=next_inspiration_run(request.schedule, now) if request.enabled else None,
        sources=[],
    )
    for source in request.sources:
        task.sources.append(
            InspirationSource(
                source_type=source.source_type,
                url=str(source.url),
                fetch_config=source.fetch_config,
            )
        )
    db.add(task)
    await db.flush()
    return _task_out(task)


@router.patch("/tasks/{task_id}", response_model=InspirationTaskOut)
async def update_task(
    task_id: str,
    request: InspirationTaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = (
        await db.execute(
            select(InspirationTask)
            .where(InspirationTask.id == task_id, InspirationTask.owner_id == user.id)
            .options(selectinload(InspirationTask.sources))
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="灵感任务不存在")
    if request.sources is not None:
        _validate_sources(request.sources)
        _sync_sources(task, request.sources)

    next_type = request.task_type or task.task_type
    next_brief = request.topic_brief if request.topic_brief is not None else task.topic_brief
    next_count = request.topic_count if request.topic_count is not None else task.topic_count
    next_discovery = (
        request.discovery_config.model_dump(mode="json")
        if request.discovery_config is not None
        else dict(task.discovery_config or {})
    )
    active_sources = request.sources if request.sources is not None else [
        source for source in task.sources if source.enabled
    ]
    if next_type == "topic-recommendation":
        if not next_brief.strip():
            raise HTTPException(status_code=422, detail="选题推荐任务必须填写选题方向")
        next_count = next_count or 5
        if next_discovery.get("source_strategy") == "only" and not active_sources:
            raise HTTPException(status_code=422, detail="仅从指定网站发现时，至少需要填写一个网站")
        if active_sources and next_discovery.get("source_strategy") == "web":
            next_discovery["source_strategy"] = "preferred"
    else:
        next_brief = ""
        next_count = None
        next_discovery["source_strategy"] = "only"
        if not active_sources:
            raise HTTPException(status_code=422, detail="来源监控至少需要填写一个链接")

    if request.name is not None:
        task.name = request.name
    task.task_type = next_type
    task.topic_brief = next_brief
    task.topic_count = next_count
    task.discovery_config = next_discovery
    if request.schedule is not None:
        task.schedule = request.schedule.model_dump(mode="json")
    if request.enabled is not None:
        task.enabled = request.enabled
    task.next_run_at = next_inspiration_run(task.schedule) if task.enabled else None
    await db.flush()
    return _task_out(task)


@router.post("/tasks/{task_id}/run", response_model=InspirationRunOut, status_code=202)
async def run_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = (
        await db.execute(
            select(InspirationTask).where(
                InspirationTask.id == task_id, InspirationTask.owner_id == user.id
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="灵感任务不存在")
    active = (
        await db.execute(
            select(InspirationRun.id).where(
                InspirationRun.task_id == task.id,
                InspirationRun.status.in_(["QUEUED", "RUNNING"]),
            )
        )
    ).first()
    if active:
        raise HTTPException(status_code=409, detail="该灵感任务已有一次运行正在执行")
    job = Job(
        owner_id=user.id,
        project_id=None,
        subject_type="inspiration_task",
        subject_id=task.id,
        name=f"灵感更新：{task.name}",
        type="灵感岛任务",
        status="QUEUED",
        stage="等待抓取",
        stages=["安全抓取", "内容去重", "AI 总结", "保存结果"],
        progress=0,
        payload={"task_id": task.id},
        eta="预计 1-3 分钟",
    )
    # Initialize the relationship so the 202 response can be serialized without
    # triggering async lazy loading after the transaction has been committed.
    run = InspirationRun(task_id=task.id, status="QUEUED", results=[])
    db.add_all([job, run])
    await db.flush()
    job.subject_id = run.id
    run.job_id = job.id
    await db.commit()

    from app.tasks.inspiration_tasks import run_inspiration_task

    try:
        celery_task = await dispatch_owner_task(
            db, user.id, run_inspiration_task, task.id, run.id, job.id
        )
        job.celery_task_id = celery_task.id
        await db.commit()
    except Exception as exc:
        run.status = "FAILED"
        run.error = f"任务派发失败：{str(exc)[:200]}"
        job.status = "FAILED"
        job.stage = "派发失败"
        job.detail = run.error
        await db.commit()
        raise HTTPException(status_code=503, detail=run.error) from exc
    return InspirationRunOut.model_validate(run)


@router.get("/tasks/{task_id}/runs", response_model=InspirationRunListOut)
async def list_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(InspirationTask, task_id)
    if not task or task.owner_id != user.id:
        raise HTTPException(status_code=404, detail="灵感任务不存在")
    total = (
        await db.execute(
            select(func.count()).select_from(InspirationRun).where(InspirationRun.task_id == task_id)
        )
    ).scalar() or 0
    rows = (
        await db.execute(
            select(InspirationRun)
            .where(InspirationRun.task_id == task_id)
            .options(selectinload(InspirationRun.results))
            .order_by(InspirationRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().unique().all()
    return InspirationRunListOut(
        items=[InspirationRunOut.model_validate(item) for item in rows],
        total=int(total),
    )


@router.get("/runs/{run_id}", response_model=InspirationRunOut)
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = (
        await db.execute(
            select(InspirationRun)
            .join(InspirationTask)
            .where(InspirationRun.id == run_id, InspirationTask.owner_id == user.id)
            .options(selectinload(InspirationRun.results))
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="灵感运行不存在")
    return InspirationRunOut.model_validate(run)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    confirmed: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除灵感任务前必须确认")
    task = await db.get(InspirationTask, task_id)
    if not task or task.owner_id != user.id:
        raise HTTPException(status_code=404, detail="灵感任务不存在")
    active = (
        await db.execute(
            select(InspirationRun.id).where(
                InspirationRun.task_id == task_id,
                InspirationRun.status.in_(["QUEUED", "RUNNING"]),
            )
        )
    ).first()
    if active:
        raise HTTPException(status_code=409, detail="任务运行中，不能删除")
    await db.delete(task)
