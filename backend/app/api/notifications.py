"""站内通知：真实列表、单条已读与全部已读。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
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
