"""站内通知：真实列表、单条已读与全部已读。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
from app.models.job import Job
from app.models.user import User


router = APIRouter()


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    job_id: str | None = None
    type: str
    title: str
    message: str
    link: str | None = None
    is_read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class NotificationFeedItemOut(NotificationOut):
    """消息中心统一数据项。

    Notification 是已产生的业务通知，Job 是仍在执行或尚未产生通知的真实任务。
    前端只消费这一份 Feed，不再维护独立任务中心。
    """

    source: str = "notification"
    status: str | None = None
    progress: int | None = None
    action_label: str | None = None


class NotificationFeedListOut(BaseModel):
    items: list[NotificationFeedItemOut]
    total: int
    unread_count: int


def _job_feed_type(status: str) -> str:
    if status == "SUCCEEDED":
        return "success"
    if status == "FAILED":
        return "error"
    return "info"


def _job_feed_link(job: Job) -> tuple[str | None, str | None]:
    if job.project_id:
        return f"/workspace/projects/{job.project_id}?job={job.id}", "打开项目"
    if job.type == "灵感采集":
        return f"/workspace/inspiration?job={job.id}", "查看灵感岛"
    if job.type == "素材处理" or job.subject_type == "asset":
        return f"/workspace/library?job={job.id}", "查看素材"
    return None, None


def _notification_action_label(notification: Notification) -> str | None:
    if not notification.link:
        return None
    if notification.link.startswith("/workspace/projects/"):
        return "打开项目"
    if notification.link.startswith("/workspace/inspiration"):
        return "查看结果"
    if notification.link.startswith("/workspace/library"):
        return "查看素材"
    return "查看详情"


@router.get("/feed", response_model=NotificationFeedListOut)
async def list_notification_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type_filter: str = Query("", alias="type"),
    read_status: str = Query("all", pattern="^(all|read|unread)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回通知和真实任务组成的统一消息流。

    已经产生 Notification 的 Job 不再单独出现，避免导出和灵感任务重复展示。
    Job 项不参与未读计数；完成或失败后，由对应业务通知继续承担未读状态。
    """

    notification_filters = [Notification.user_id == user.id]
    if type_filter and type_filter != "task":
        notification_filters.append(Notification.type == type_filter)
    elif type_filter == "task":
        notification_filters.append(Notification.job_id.is_not(None))
    if read_status == "read":
        notification_filters.append(Notification.is_read.is_(True))
    elif read_status == "unread":
        notification_filters.append(Notification.is_read.is_(False))

    notification_total = (
        await db.execute(
            select(func.count()).select_from(Notification).where(*notification_filters)
        )
    ).scalar() or 0
    unread_count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        )
    ).scalar() or 0

    window_size = page * page_size
    notification_result = await db.execute(
        select(Notification)
        .where(*notification_filters)
        .order_by(Notification.created_at.desc())
        .limit(window_size)
    )
    notifications = notification_result.scalars().all()
    notification_job_ids = {item.job_id for item in notifications if item.job_id}
    notification_jobs: dict[str, Job] = {}
    if notification_job_ids:
        linked_job_result = await db.execute(
            select(Job).where(Job.owner_id == user.id, Job.id.in_(notification_job_ids))
        )
        notification_jobs = {item.id: item for item in linked_job_result.scalars().all()}

    jobs: list[Job] = []
    job_total = 0
    if read_status != "unread":
        notified_job_exists = (
            select(Notification.id)
            .where(Notification.job_id == Job.id)
            .exists()
        )
        job_filters = [Job.owner_id == user.id, ~notified_job_exists]
        if type_filter == "success":
            job_filters.append(Job.status == "SUCCEEDED")
        elif type_filter == "error":
            job_filters.append(Job.status == "FAILED")
        elif type_filter == "info":
            job_filters.append(Job.status.in_(["QUEUED", "RUNNING", "PAUSED", "CANCELLED"]))
        elif type_filter and type_filter != "task":
            job_filters.append(Job.id == "")

        job_total = (
            await db.execute(select(func.count()).select_from(Job).where(*job_filters))
        ).scalar() or 0
        job_result = await db.execute(
            select(Job)
            .where(*job_filters)
            .order_by(Job.updated_at.desc(), Job.created_at.desc())
            .limit(window_size)
        )
        jobs = list(job_result.scalars().all())

    feed_items: list[NotificationFeedItemOut] = []
    for notification in notifications:
        linked_job = notification_jobs.get(notification.job_id or "")
        project_id = notification.project_id or (linked_job.project_id if linked_job else None)
        link = notification.link
        action_label = _notification_action_label(notification)
        if link and (
            link.startswith("/workspace/scripts/")
            or link.startswith("/workspace/tasks")
            or (link.startswith("/workspace/projects/") and "/editor" in link)
        ):
            link = f"/workspace/projects/{project_id}" if project_id else None
            action_label = "打开项目" if project_id else None
        if not link and linked_job:
            link, action_label = _job_feed_link(linked_job)
        feed_items.append(
            NotificationFeedItemOut(
                id=notification.id,
                project_id=project_id,
                job_id=notification.job_id,
                type=notification.type,
                title=notification.title,
                message=notification.message,
                link=link,
                is_read=notification.is_read,
                created_at=notification.created_at,
                source="notification",
                action_label=action_label,
            )
        )
    for job in jobs:
        link, action_label = _job_feed_link(job)
        feed_items.append(
            NotificationFeedItemOut(
                id=job.id,
                project_id=job.project_id,
                job_id=job.id,
                type=_job_feed_type(job.status),
                title=job.name or job.type or "后台任务",
                message=job.detail or job.stage or "任务状态已更新",
                link=link,
                is_read=True,
                created_at=job.updated_at or job.created_at,
                source="job",
                status=job.status,
                progress=job.progress,
                action_label=action_label,
            )
        )

    feed_items.sort(key=lambda item: item.created_at, reverse=True)
    offset = (page - 1) * page_size
    return NotificationFeedListOut(
        items=feed_items[offset:offset + page_size],
        total=notification_total + job_total,
        unread_count=unread_count,
    )


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type_filter: str = Query("", alias="type"),
    read_status: str = Query("all", pattern="^(all|read|unread)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [Notification.user_id == user.id]
    if type_filter:
        filters.append(Notification.type == type_filter)
    if read_status == "read":
        filters.append(Notification.is_read.is_(True))
    elif read_status == "unread":
        filters.append(Notification.is_read.is_(False))

    base = select(Notification).where(*filters)
    total = (
        await db.execute(
            select(func.count()).select_from(Notification).where(*filters)
        )
    ).scalar() or 0
    unread_count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        )
    ).scalar() or 0
    result = await db.execute(
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return NotificationListOut(
        items=[NotificationOut.model_validate(item) for item in result.scalars().all()],
        total=total,
        unread_count=unread_count,
    )


@router.post("/read-all")
async def mark_all_notifications_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    return {"updated": result.rowcount or 0}


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification.is_read = True
    await db.flush()
    return NotificationOut.model_validate(notification)
