"""统一项目访问控制，供所有业务路由复用。"""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import ProjectMember
from app.models.project import Project
from app.models.user import User


ROLE_LEVEL = {"viewer": 1, "editor": 2, "owner": 3}


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    role: str


def accessible_project_condition(user_id: str):
    """返回可用于 Project 查询的 owner/member 访问条件。"""
    return or_(
        Project.owner_id == user_id,
        exists(
            select(ProjectMember.id).where(
                ProjectMember.project_id == Project.id,
                ProjectMember.user_id == user_id,
            )
        ),
    )


async def require_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    minimum_role: str = "viewer",
) -> ProjectAccess:
    """取得项目与当前角色；无读取权限返回 404，角色不足返回 403。"""
    result = await db.execute(
        select(Project, ProjectMember.role)
        .outerjoin(
            ProjectMember,
            and_(
                ProjectMember.project_id == Project.id,
                ProjectMember.user_id == user.id,
            ),
        )
        .where(Project.id == project_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")

    project, member_role = row
    role = "owner" if project.owner_id == user.id else member_role
    if role not in ROLE_LEVEL:
        raise HTTPException(status_code=404, detail="项目不存在")
    if ROLE_LEVEL[role] < ROLE_LEVEL[minimum_role]:
        role_name = {"editor": "编辑者", "owner": "所有者"}[minimum_role]
        raise HTTPException(status_code=403, detail=f"该操作需要项目{role_name}权限")
    return ProjectAccess(project=project, role=role)


async def require_resource_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    minimum_role: str = "viewer",
) -> Project:
    return (await require_project_access(project_id, user, db, minimum_role)).project
