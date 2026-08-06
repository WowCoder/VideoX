"""跨项目、脚本、素材和片段的真实全局搜索。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, Clip
from app.models.project import Project
from app.models.script import Script
from app.models.user import User
from app.services.project_access import accessible_project_condition


router = APIRouter()


class SearchItem(BaseModel):
    type: str
    id: str
    title: str
    subtitle: str = ""
    project_id: str | None = None
    url: str


class SearchResponse(BaseModel):
    query: str
    items: list[SearchItem]
    total: int


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索当前用户拥有或参与的真实业务数据，每类最多返回 limit 条。"""
    query_text = q.strip()
    if not query_text:
        return SearchResponse(query="", items=[], total=0)
    pattern = f"%{query_text}%"
    items: list[SearchItem] = []

    projects = (
        await db.execute(
            select(Project)
            .where(
                accessible_project_condition(user.id),
                or_(
                    Project.name.ilike(pattern),
                    Project.description.ilike(pattern),
                    Project.type.ilike(pattern),
                ),
            )
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    items.extend(
        SearchItem(
            type="project",
            id=project.id,
            title=project.name,
            subtitle=project.description or project.type,
            project_id=project.id,
            url=f"/workspace/projects/{project.id}",
        )
        for project in projects
    )

    scripts = (
        await db.execute(
            select(Script)
            .join(Project, Script.project_id == Project.id)
            .where(
                accessible_project_condition(user.id),
                or_(Script.title.ilike(pattern), Script.summary.ilike(pattern)),
            )
            .order_by(Script.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    items.extend(
        SearchItem(
            type="script",
            id=script.id,
            title=script.title,
            subtitle=script.summary or script.status,
            project_id=script.project_id,
            url=f"/workspace/scripts/{script.id}/editor",
        )
        for script in scripts
    )

    assets = (
        await db.execute(
            select(Asset)
            .join(Project, Asset.project_id == Project.id)
            .where(
                accessible_project_condition(user.id),
                or_(
                    Asset.name.ilike(pattern),
                    Asset.transcript.ilike(pattern),
                    Asset.ocr_text.ilike(pattern),
                    cast(Asset.tags, String).ilike(pattern),
                ),
            )
            .order_by(Asset.uploaded_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    items.extend(
        SearchItem(
            type="asset",
            id=asset.id,
            title=asset.name,
            subtitle=f"{asset.status} · {asset.source}",
            project_id=asset.project_id,
            url="/workspace/library",
        )
        for asset in assets
    )

    clips = (
        await db.execute(
            select(Clip, Asset.project_id, Asset.name)
            .join(Asset, Clip.asset_id == Asset.id)
            .join(Project, Asset.project_id == Project.id)
            .where(
                accessible_project_condition(user.id),
                or_(
                    Clip.title.ilike(pattern),
                    Clip.transcript_segment.ilike(pattern),
                    Clip.ocr_segment.ilike(pattern),
                ),
            )
            .order_by(Clip.created_at.desc())
            .limit(limit)
        )
    ).all()
    items.extend(
        SearchItem(
            type="clip",
            id=clip.id,
            title=clip.title or f"{asset_name} 片段",
            subtitle=f"{asset_name} · {clip.start_time:.1f}s–{clip.end_time:.1f}s",
            project_id=project_id,
            url="/workspace/library",
        )
        for clip, project_id, asset_name in clips
    )

    return SearchResponse(query=query_text, items=items, total=len(items))
