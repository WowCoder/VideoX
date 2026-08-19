"""项目聚合、工作区、素材关联、版本与可逆删除 API。"""

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, ProjectAssetLink
from app.models.job import Job
from app.models.project import Project, ProjectComposition, ProjectRevision
from app.models.script import Script, ScriptUnit
from app.models.user import User
from app.schemas.asset import AssetLinkRequest, AssetOut
from app.schemas.project import (
    DeleteMutationOut,
    ProjectCreate,
    ProjectListOut,
    ProjectOut,
    ProjectUpdate,
    UndoRequest,
    WorkspaceOut,
    WorkspaceSave,
)
from app.services.project_access import require_project_access
from app.services.workspace import (
    delete_scene,
    delete_shot,
    load_project_workspace,
    project_out,
    record_revision,
    save_workspace,
    undo_mutation,
    workspace_out,
)


router = APIRouter()


def _idempotent_project_id(user_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{key}".encode("utf-8")).hexdigest()[:24]
    return f"project-{digest}"


async def _list_project_out(db: AsyncSession, project: Project) -> ProjectOut:
    return await project_out(db, project)


@router.get("", response_model=ProjectListOut)
async def list_projects(
    search: str = Query(""),
    status_filter: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [Project.owner_id == user.id]
    if search:
        keyword = f"%{search.strip()}%"
        filters.append(
            or_(
                Project.name.ilike(keyword),
                Project.type.ilike(keyword),
                Project.description.ilike(keyword),
            )
        )
    if status_filter:
        filters.append(Project.status == status_filter)
    total = (
        await db.execute(select(func.count()).select_from(Project).where(*filters))
    ).scalar() or 0
    projects = (
        await db.execute(
            select(Project)
            .where(*filters)
            .options(
                selectinload(Project.composition),
                selectinload(Project.asset_links).selectinload(ProjectAssetLink.asset),
                selectinload(Project.script)
                .selectinload(Script.units)
                .selectinload(ScriptUnit.shots),
            )
            .order_by(Project.updated_at.desc(), Project.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().unique().all()
    return ProjectListOut(
        items=[await _list_project_out(db, item) for item in projects], total=int(total)
    )


@router.get("/dashboard-summary")
async def dashboard_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_count = (
        await db.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == user.id)
        )
    ).scalar() or 0
    asset_count = (
        await db.execute(
            select(func.count()).select_from(Asset).where(
                Asset.owner_id == user.id, Asset.deleted_at.is_(None)
            )
        )
    ).scalar() or 0
    segment_count = (
        await db.execute(
            select(func.count()).select_from(ProjectAssetLink).join(Asset).where(
                Asset.owner_id == user.id, Asset.deleted_at.is_(None)
            )
        )
    ).scalar() or 0
    job_counts = dict(
        (
            await db.execute(
                select(Job.status, func.count(Job.id))
                .where(Job.owner_id == user.id)
                .group_by(Job.status)
            )
        ).all()
    )
    return {
        "project_count": int(project_count),
        "asset_count": int(asset_count),
        "linked_asset_count": int(segment_count),
        "queued_job_count": int(job_counts.get("QUEUED", 0)),
        "running_job_count": int(job_counts.get("RUNNING", 0)),
        "paused_job_count": int(job_counts.get("PAUSED", 0)),
        "completed_job_count": int(job_counts.get("SUCCEEDED", 0)),
        "failed_job_count": int(job_counts.get("FAILED", 0)),
    }


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_project(
    request: ProjectCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """点击“创建并开始”后原子创建项目、唯一脚本、唯一主成片和初始版本。"""
    project_id = _idempotent_project_id(user.id, idempotency_key)
    existing = await db.get(Project, project_id)
    if existing:
        if existing.owner_id != user.id:
            raise HTTPException(status_code=409, detail="幂等键冲突")
        project = await load_project_workspace(db, existing.id, user.id)
        return await workspace_out(db, project)

    project = Project(
        id=project_id,
        owner_id=user.id,
        name=request.name,
        initial=request.name[0].upper(),
        type=request.type,
        description=request.description,
        variant=request.variant,
        status="draft",
    )
    script = Script(
        project=project,
        title=request.script_title or request.name,
        status="editing",
        target_duration_seconds=request.target_duration_seconds,
        estimated_duration_seconds=0,
        revision=0,
        source_type="blank",
        units=[],
    )
    composition = ProjectComposition(
        project=project,
        revision=0,
        aspect_ratio=request.aspect_ratio,
    )
    db.add_all([project, script, composition])
    await db.flush()
    await record_revision(db, project, user.id, "initial")
    await db.flush()
    project = await load_project_workspace(db, project.id, user.id)
    return await workspace_out(db, project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id)
    return await project_out(db, project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    request: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return await project_out(db, project)


@router.get("/{project_id}/workspace", response_model=WorkspaceOut)
async def get_workspace(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id)
    return await workspace_out(db, project)


@router.patch("/{project_id}/workspace", response_model=WorkspaceOut)
async def patch_workspace(
    project_id: str,
    request: WorkspaceSave,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    await save_workspace(db, project, user, request)
    project = await load_project_workspace(db, project_id, user.id)
    return await workspace_out(db, project)


@router.post("/{project_id}/assets/{asset_id}", response_model=AssetOut)
async def link_asset(
    project_id: str,
    asset_id: str,
    request: AssetLinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "editor")
    asset = await db.get(Asset, asset_id)
    if not asset or asset.owner_id != user.id or asset.deleted_at:
        raise HTTPException(status_code=404, detail="素材不存在")
    existing = (
        await db.execute(
            select(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.asset_id == asset_id,
                ProjectAssetLink.role == request.role,
            )
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(
            ProjectAssetLink(
                project_id=project_id,
                asset_id=asset_id,
                role=request.role,
                linked_by=user.id,
            )
        )
        await db.flush()
    from app.api.assets import asset_out

    return asset_out(asset, include_segments=False, project_ids=[project_id])


@router.delete("/{project_id}/assets/{asset_id}", status_code=204)
async def unlink_asset(
    project_id: str,
    asset_id: str,
    role: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id)
    if any(
        shot.asset_id == asset_id
        for scene in project.script.units
        for shot in scene.shots
    ):
        raise HTTPException(status_code=409, detail="素材仍被项目镜头使用，不能解除关联")
    links = (
        await db.execute(
            select(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.asset_id == asset_id,
            )
        )
    ).scalars().all()
    removed = False
    for link in links:
        if role is None or link.role == role:
            await db.delete(link)
            removed = True
    if not removed:
        raise HTTPException(status_code=404, detail="项目未关联该素材")


@router.delete("/{project_id}/scenes/{scene_id}", response_model=DeleteMutationOut)
async def remove_scene(
    project_id: str,
    scene_id: str,
    expected_revision: int = Query(..., ge=0),
    confirmed: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除场景前必须确认影响范围")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    token = await delete_scene(db, project, user, scene_id, expected_revision)
    project = await load_project_workspace(db, project_id, user.id)
    return DeleteMutationOut(
        workspace=await workspace_out(db, project),
        undo_token=token.id,
        undo_expires_at=token.expires_at,
    )


@router.delete("/{project_id}/shots/{shot_id}", response_model=DeleteMutationOut)
async def remove_shot(
    project_id: str,
    shot_id: str,
    expected_revision: int = Query(..., ge=0),
    confirmed: bool = Query(True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除镜头前必须确认")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    token = await delete_shot(db, project, user, shot_id, expected_revision)
    project = await load_project_workspace(db, project_id, user.id)
    return DeleteMutationOut(
        workspace=await workspace_out(db, project),
        undo_token=token.id,
        undo_expires_at=token.expires_at,
    )


@router.post("/{project_id}/undo", response_model=WorkspaceOut)
async def undo_project_mutation(
    project_id: str,
    request: UndoRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    await undo_mutation(db, project, user, request.token)
    project = await load_project_workspace(db, project_id, user.id)
    return await workspace_out(db, project)


@router.get("/{project_id}/revisions")
async def list_revisions(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db)
    rows = (
        await db.execute(
            select(ProjectRevision)
            .where(ProjectRevision.project_id == project_id)
            .order_by(ProjectRevision.revision.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": item.id,
            "revision": item.revision,
            "reason": item.reason,
            "metadata": item.revision_metadata,
            "created_at": item.created_at,
        }
        for item in rows
    ]


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    confirmed: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除项目前必须确认")
    project = (await require_project_access(project_id, user, db, "owner")).project
    await db.delete(project)
