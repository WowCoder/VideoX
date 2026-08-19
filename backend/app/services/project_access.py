"""项目所有者访问控制；本版本不提供多人协作。"""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    role: str = "owner"


def accessible_project_condition(user_id: str):
    return Project.owner_id == user_id


async def require_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    minimum_role: str = "viewer",
) -> ProjectAccess:
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.owner_id == user.id)
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return ProjectAccess(project=project)


async def require_resource_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    minimum_role: str = "viewer",
) -> Project:
    return (await require_project_access(project_id, user, db, minimum_role)).project
