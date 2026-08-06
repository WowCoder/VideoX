"""项目路由：CRUD + 列表。"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.asset import Asset, Clip
from app.models.script import Candidate, Script, ScriptUnit, Shot
from app.models.job import Job
from app.models.collaboration import ProjectMember
from app.models.project_media import ProjectMediaItem
from app.services.project_access import accessible_project_condition, require_project_access
from app.services.timeline_validation import TimelineValidationError, validate_project_timeline
from app.config import get_settings
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectOut,
    ProjectListOut,
    ProjectTimelineOut,
    ProjectTimelineUpdate,
    ProjectMediaItemOut,
    ProjectMediaListOut,
)

router = APIRouter()
settings = get_settings()


def _timeline_clips_for_output(clips: list[dict] | None) -> list[dict]:
    """为 AI 生成媒体补充临时访问地址，不把签名 URL 写回持久化时间线。"""
    from app.utils.storage import get_file_url

    output: list[dict] = []
    for raw_clip in clips or []:
        clip = dict(raw_clip)
        path = clip.get("generated_media_path")
        if path:
            if str(path).startswith(("http://", "https://", "data:")):
                clip["generated_media_url"] = str(path)
            else:
                try:
                    clip["generated_media_url"] = get_file_url(str(path))
                except Exception:
                    clip["generated_media_url"] = None
        output.append(clip)
    return output


async def _project_outs(
    projects: list[Project], db: AsyncSession, current_user_id: str
) -> list[ProjectOut]:
    """使用真实聚合统计序列化项目，避免冗余计数字段漂移影响界面。"""
    if not projects:
        return []
    project_ids = [project.id for project in projects]
    asset_counts = dict(
        (
            await db.execute(
                select(Asset.project_id, func.count(Asset.id))
                .where(Asset.project_id.in_(project_ids))
                .group_by(Asset.project_id)
            )
        ).all()
    )
    searchable_clip_counts = dict(
        (
            await db.execute(
                select(Asset.project_id, func.count(Clip.id))
                .join(Clip, Clip.asset_id == Asset.id)
                .where(
                    Asset.project_id.in_(project_ids),
                    Clip.embedding.is_not(None),
                    Clip.embedding_model == settings.active_embedding_model,
                    Clip.embedding_dimensions == settings.ai_embedding_dimensions,
                    Clip.embedding_status == "ready",
                )
                .group_by(Asset.project_id)
            )
        ).all()
    )
    script_counts = dict(
        (
            await db.execute(
                select(Script.project_id, func.count(Script.id))
                .where(Script.project_id.in_(project_ids))
                .group_by(Script.project_id)
            )
        ).all()
    )
    owner_initials = dict(
        (
            await db.execute(
                select(User.id, User.avatar_initial).where(
                    User.id.in_({project.owner_id for project in projects})
                )
            )
        ).all()
    )
    member_rows = (
        await db.execute(
            select(
                ProjectMember.project_id,
                ProjectMember.user_id,
                ProjectMember.role,
                User.avatar_initial,
            )
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id.in_(project_ids))
            .order_by(ProjectMember.joined_at)
        )
    ).all()
    member_initials: dict[str, list[str]] = {project_id: [] for project_id in project_ids}
    current_roles: dict[str, str] = {}
    for project_id, member_user_id, role, initial in member_rows:
        member_initials[project_id].append(initial)
        if member_user_id == current_user_id:
            current_roles[project_id] = role
    return [
        ProjectOut.model_validate(project).model_copy(
            update={
                "asset_count": int(asset_counts.get(project.id, 0)),
                "clip_count": int(searchable_clip_counts.get(project.id, 0)),
                "script_count": int(script_counts.get(project.id, 0)),
                "members": [owner_initials.get(project.owner_id, "U")]
                + member_initials.get(project.id, []),
                "current_user_role": (
                    "owner" if project.owner_id == current_user_id
                    else current_roles.get(project.id, "viewer")
                ),
            }
        )
        for project in projects
    ]


@router.get("", response_model=ProjectListOut)
async def list_projects(
    search: str = Query("", description="搜索关键词"),
    status_filter: str = Query("", alias="status", description="状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目列表。"""
    query = select(Project).where(accessible_project_condition(user.id))

    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))
    if status_filter:
        query = query.where(Project.status == status_filter)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    query = query.order_by(desc(Project.updated_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    projects = result.scalars().all()

    return ProjectListOut(
        items=await _project_outs(list(projects), db, user.id),
        total=total,
    )


@router.get("/dashboard-summary")
async def get_dashboard_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """工作台全局统计，避免前端从分页列表推算总数。"""
    project_count = (await db.execute(
        select(func.count()).where(accessible_project_condition(user.id))
    )).scalar() or 0
    asset_count = (await db.execute(
        select(func.count()).select_from(Asset).join(Project).where(accessible_project_condition(user.id))
    )).scalar() or 0
    processing_asset_count = (await db.execute(
        select(func.count()).select_from(Asset).join(Project).where(
            accessible_project_condition(user.id),
            Asset.status.in_(["处理中", "AI 处理中"]),
        )
    )).scalar() or 0
    clip_count = (await db.execute(
        select(func.count()).select_from(Clip).join(Asset).join(Project).where(
            accessible_project_condition(user.id),
            Clip.embedding.is_not(None),
            Clip.embedding_model == settings.active_embedding_model,
            Clip.embedding_dimensions == settings.ai_embedding_dimensions,
            Clip.embedding_status == "ready",
        )
    )).scalar() or 0
    script_count = (await db.execute(
        select(func.count()).select_from(Script).join(
            Project, Script.project_id == Project.id
        ).where(accessible_project_condition(user.id))
    )).scalar() or 0

    job_counts = {}
    for status in ("QUEUED", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED"):
        job_counts[status.lower()] = (await db.execute(
            select(func.count()).select_from(Job).join(Project).where(
                accessible_project_condition(user.id),
                Job.status == status,
            )
        )).scalar() or 0

    return {
        "project_count": project_count,
        "asset_count": asset_count,
        "processing_asset_count": processing_asset_count,
        "clip_count": clip_count,
        "script_count": script_count,
        "queued_job_count": job_counts["queued"],
        "running_job_count": job_counts["running"],
        "paused_job_count": job_counts["paused"],
        "completed_job_count": job_counts["succeeded"],
        "failed_job_count": job_counts["failed"],
    }


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    req: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建项目。"""
    project = Project(
        owner_id=user.id,
        name=req.name,
        initial=req.name[0].upper() if req.name else "P",
        type=req.type,
        description=req.description,
        variant=req.variant,
        status="等待上传",
        is_new=True,
    )
    db.add(project)
    await db.flush()
    return (await _project_outs([project], db, user.id))[0]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目详情。"""
    project = (await require_project_access(project_id, user, db)).project
    return (await _project_outs([project], db, user.id))[0]


def _project_media_out(item: ProjectMediaItem) -> ProjectMediaItemOut:
    from app.api.assets import _asset_out
    from app.utils.storage import get_file_url

    media_url = None
    thumbnail_url = None
    if item.asset:
        asset_out = _asset_out(item.asset)
        media_url = asset_out.media_url
        thumbnail_url = asset_out.thumbnail_url
    else:
        asset_out = None
        if item.storage_path:
            try:
                media_url = get_file_url(item.storage_path)
            except Exception:
                media_url = None
        thumbnail_path = item.thumbnail_path or (
            item.storage_path if item.media_type == "image" else None
        )
        if thumbnail_path:
            try:
                thumbnail_url = get_file_url(thumbnail_path)
            except Exception:
                thumbnail_url = None

    return ProjectMediaItemOut(
        id=item.id,
        project_id=item.project_id,
        kind=item.kind,
        asset_id=item.asset_id,
        storage_path=item.storage_path,
        media_type=item.media_type,
        source_project_id=item.source_project_id,
        source_script_id=item.source_script_id,
        source_shot_id=item.source_shot_id,
        name=item.name,
        duration=item.duration or 0,
        media_url=media_url,
        thumbnail_url=thumbnail_url,
        asset=asset_out,
        created_at=item.created_at,
    )


@router.get("/{project_id}/media", response_model=ProjectMediaListOut)
async def list_project_media(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取已逻辑导入项目素材箱的来源素材和 AI 生成媒体。"""
    await require_project_access(project_id, user, db)
    items = (
        await db.execute(
            select(ProjectMediaItem)
            .where(ProjectMediaItem.project_id == project_id)
            .options(selectinload(ProjectMediaItem.asset).selectinload(Asset.clips))
            .order_by(desc(ProjectMediaItem.created_at))
        )
    ).scalars().all()
    return ProjectMediaListOut(
        items=[_project_media_out(item) for item in items],
        total=len(items),
    )


@router.post("/{project_id}/media/sync", response_model=ProjectMediaListOut)
async def sync_project_media(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从持久化时间线和初剪快照补齐项目媒体索引，不改写人工时间线。"""
    project = (await require_project_access(project_id, user, db, "editor")).project
    snapshot = (
        await db.execute(
            select(Script)
            .where(Script.project_id == project.id, Script.is_snapshot.is_(True))
            .options(selectinload(Script.units).selectinload(ScriptUnit.shots))
            .order_by(desc(Script.created_at))
        )
    ).scalars().first()
    from app.services.project_media import sync_project_media_items

    await sync_project_media_items(db, project, snapshot)
    await db.flush()
    return await list_project_media(project_id, user, db)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    req: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新项目。"""
    project = (await require_project_access(project_id, user, db, "editor")).project

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    await db.flush()
    return (await _project_outs([project], db, user.id))[0]


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除无外部依赖且没有运行任务的项目。"""
    project = (await require_project_access(project_id, user, db, "owner")).project

    from app.services.deletion import project_delete_impact, project_storage_paths

    impact = await project_delete_impact(db, project)
    if not impact["can_delete"]:
        raise HTTPException(status_code=409, detail="；".join(impact["blockers"]))

    object_paths = await project_storage_paths(db, project.id)
    script_ids = list(
        (await db.execute(select(Script.id).where(Script.project_id == project.id))).scalars().all()
    )
    if script_ids:
        unit_ids = list(
            (
                await db.execute(
                    select(ScriptUnit.id).where(ScriptUnit.script_id.in_(script_ids))
                )
            ).scalars().all()
        )
        shot_ids = list(
            (await db.execute(select(Shot.id).where(Shot.unit_id.in_(unit_ids)))).scalars().all()
        ) if unit_ids else []
        if unit_ids:
            await db.execute(delete(Candidate).where(Candidate.unit_id.in_(unit_ids)))
        if shot_ids:
            await db.execute(delete(Candidate).where(Candidate.shot_id.in_(shot_ids)))
    project.source_script_id = None
    await db.flush()

    await db.delete(project)
    await db.commit()

    from app.utils.storage import delete_file

    for path in object_paths:
        delete_file(path)


@router.get("/{project_id}/delete-impact")
async def get_project_delete_impact(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = (await require_project_access(project_id, user, db, "owner")).project
    from app.services.deletion import project_delete_impact

    return await project_delete_impact(db, project)


@router.get("/{project_id}/stats")
async def get_project_stats(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目统计信息。"""
    await require_project_access(project_id, user, db)
    asset_count = (await db.execute(
        select(func.count()).where(Asset.project_id == project_id)
    )).scalar() or 0

    clip_count = (await db.execute(
        select(func.count()).select_from(Clip).join(Asset).where(
            Asset.project_id == project_id,
            Clip.embedding.is_not(None),
            Clip.embedding_model == settings.active_embedding_model,
            Clip.embedding_dimensions == settings.ai_embedding_dimensions,
            Clip.embedding_status == "ready",
        )
    )).scalar() or 0

    script_count = (await db.execute(
        select(func.count()).where(Script.project_id == project_id)
    )).scalar() or 0

    total_duration = (await db.execute(
        select(func.coalesce(func.sum(Asset.duration), 0.0)).where(Asset.project_id == project_id)
    )).scalar() or 0.0

    storage_used_mb = (await db.execute(
        select(func.coalesce(func.sum(Asset.file_size_mb), 0.0)).where(Asset.project_id == project_id)
    )).scalar() or 0.0

    job_count = (await db.execute(
        select(func.count()).where(Job.project_id == project_id)
    )).scalar() or 0

    return {
        "asset_count": asset_count,
        "clip_count": clip_count,
        "script_count": script_count,
        "job_count": job_count,
        "total_duration": float(total_duration),
        "storage_used_mb": float(storage_used_mb),
    }


@router.get("/{project_id}/timeline", response_model=ProjectTimelineOut)
async def get_project_timeline(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取项目剪辑时间线；未编辑过的项目返回真实空时间线。"""
    project = (await require_project_access(project_id, user, db)).project
    return ProjectTimelineOut(
        project_id=project.id,
        version=project.timeline_version or 0,
        aspect_ratio=project.aspect_ratio or "16:9",
        clips=_timeline_clips_for_output(project.timeline),
        updated_at=project.timeline_updated_at,
    )


@router.put("/{project_id}/timeline", response_model=ProjectTimelineOut)
async def save_project_timeline(
    project_id: str,
    req: ProjectTimelineUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存完整时间线，并用版本号避免多个页面互相覆盖。"""
    project = (await require_project_access(project_id, user, db, "editor")).project
    current_version = project.timeline_version or 0
    if req.version != current_version:
        raise HTTPException(status_code=409, detail="时间线已在其他页面更新，请刷新后重试")

    try:
        await validate_project_timeline(project, req.clips, db, user, allow_placeholders=True)
    except TimelineValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    project.timeline = [
        clip.model_dump(mode="json", exclude={"generated_media_url"})
        for clip in req.clips
    ]
    project.timeline_version = current_version + 1
    project.timeline_updated_at = now
    project.aspect_ratio = req.aspect_ratio
    from app.services.project_media import sync_project_media_items

    await sync_project_media_items(db, project)
    await db.flush()

    return ProjectTimelineOut(
        project_id=project.id,
        version=project.timeline_version,
        aspect_ratio=project.aspect_ratio,
        clips=_timeline_clips_for_output(project.timeline),
        updated_at=now,
    )


@router.post("/{project_id}/timeline/assemble-from-script", response_model=ProjectTimelineOut)
async def assemble_project_timeline_from_script(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为历史空剪辑项目按初剪快照补装完整时间线，不覆盖已有人工剪辑。"""
    project = (await require_project_access(project_id, user, db, "editor")).project
    if project.timeline:
        raise HTTPException(status_code=409, detail="当前项目已有时间线内容，不能重新装配覆盖")
    if not project.source_script_id:
        raise HTTPException(status_code=400, detail="当前项目没有关联来源脚本")

    snapshot = (
        await db.execute(
            select(Script)
            .where(Script.project_id == project.id, Script.is_snapshot.is_(True))
            .options(selectinload(Script.units).selectinload(ScriptUnit.shots))
            .order_by(desc(Script.created_at))
        )
    ).scalars().first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="当前项目没有可用于装配的初剪脚本快照")

    media_by_shot: dict[str, dict] = {}
    for unit in snapshot.units:
        for shot in unit.shots or []:
            if shot.selected_clip_id:
                source_clip = await db.get(Clip, shot.selected_clip_id)
                asset = await db.get(Asset, source_clip.asset_id) if source_clip else None
                if source_clip and asset and asset.file_path:
                    ranged_duration = float(source_clip.end_time or 0) - float(source_clip.start_time or 0)
                    source_duration = ranged_duration if ranged_duration > 0 else float(source_clip.duration or 0)
                    if source_duration > 0:
                        media_by_shot[shot.id] = {
                            "kind": "asset",
                            "asset_id": asset.id,
                            "source_clip_id": source_clip.id,
                            "source_start": float(source_clip.start_time or 0),
                            "source_duration": source_duration,
                            "name": source_clip.title or asset.name,
                            "variant": source_clip.variant or asset.variant or "stage",
                        }
                        continue

            generated_path = (
                shot.generated_video_path
                or shot.generated_effect_video_path
                or shot.generated_image_path
            )
            if generated_path:
                media_by_shot[shot.id] = {
                    "kind": "generated",
                    "generated_media_path": generated_path,
                    "generated_media_type": (
                        "video"
                        if shot.generated_video_path or shot.generated_effect_video_path
                        else "image"
                    ),
                    "name": shot.description or "AI 生成分镜",
                    "variant": "robot",
                }

    from app.tasks.roughcut_tasks import _assemble_script_timeline

    timeline, stats = _assemble_script_timeline(snapshot, media_by_shot)
    if not any(item.get("track") == "video" for item in timeline):
        raise HTTPException(status_code=400, detail="脚本中没有可用于装配时间线的内容")

    now = datetime.now(timezone.utc)
    project.timeline = timeline
    project.timeline_version = (project.timeline_version or 0) + 1
    project.timeline_updated_at = now
    project.ai_shot_count = stats["generated"]
    project.status = "AI 初剪可编辑"
    project.description = (
        f"已按脚本时间线装配 {stats['matched']} 个真实素材镜头"
        + (f"、{stats['generated']} 个 AI 生成镜头" if stats["generated"] else "")
        + (f"，仍有 {stats['placeholder']} 处待补齐。" if stats["placeholder"] else "，可继续精剪并导出。")
    )
    from app.services.project_media import sync_project_media_items

    await sync_project_media_items(db, project, snapshot)
    await db.flush()

    return ProjectTimelineOut(
        project_id=project.id,
        version=project.timeline_version,
        aspect_ratio=project.aspect_ratio or "16:9",
        clips=_timeline_clips_for_output(project.timeline),
        updated_at=now,
    )
