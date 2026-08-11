"""Membership-aware Celery dispatch for all user-triggered background jobs."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.user import User
from app.services.subscriptions import reconcile_user_subscription


FREE_TASK_PRIORITY = 9
PRO_TASK_PRIORITY = 4
TEAM_TASK_PRIORITY = 0


def task_priority_for_rank(rank: int) -> int:
    """Celery uses 0 as highest and 9 as lowest priority."""
    if rank >= 2:
        return TEAM_TASK_PRIORITY
    if rank >= 1:
        return PRO_TASK_PRIORITY
    return FREE_TASK_PRIORITY


async def dispatch_project_task(
    db: AsyncSession,
    project_id: str,
    task: Any,
    *args: Any,
):
    """Dispatch using the project owner's current plan, including collaborator requests."""
    owner = (
        await db.execute(
            select(User)
            .join(Project, Project.owner_id == User.id)
            .where(Project.id == project_id)
            .options(
                selectinload(User.membership),
                selectinload(User.subscription),
            )
        )
    ).scalar_one()
    await reconcile_user_subscription(db, owner)
    rank = owner.membership.rank if owner.membership else 0
    return task.apply_async(args=args, priority=task_priority_for_rank(rank))
