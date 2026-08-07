"""删除影响分析与对象存储清理信息收集。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, Clip
from app.models.job import Job
from app.models.project import Project
from app.models.project_media import ProjectMediaItem
from app.models.script import Candidate, Script, ScriptUnit, Shot, ShotGeneration
from app.models.cut_version import CutVersion


ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING", "PAUSED"}


def _timeline_asset_references(timeline: list[dict] | None, asset_id: str) -> int:
    return sum(1 for item in timeline or [] if str(item.get("asset_id") or "") == asset_id)


async def asset_delete_impact(db: AsyncSession, asset: Asset) -> dict[str, Any]:
    clip_ids = list(
        (await db.execute(select(Clip.id).where(Clip.asset_id == asset.id))).scalars().all()
    )
    unit_refs = shot_refs = candidate_refs = 0
    if clip_ids:
        unit_refs = int(
            (await db.execute(select(func.count()).where(ScriptUnit.selected_clip_id.in_(clip_ids)))).scalar()
            or 0
        )
        shot_refs = int(
            (await db.execute(select(func.count()).where(Shot.selected_clip_id.in_(clip_ids)))).scalar()
            or 0
        )
        candidate_refs = int(
            (await db.execute(select(func.count()).where(Candidate.clip_id.in_(clip_ids)))).scalar()
            or 0
        )

    media_refs = int(
        (await db.execute(select(func.count()).where(ProjectMediaItem.asset_id == asset.id))).scalar()
        or 0
    )
    timeline_refs = 0
    version_rows = (
        await db.execute(select(CutVersion.project_id, CutVersion.timeline))
    ).all()
    version_project_ids = {project_id for project_id, _ in version_rows}
    project_rows = (
        await db.execute(select(Project.id, Project.timeline).where(Project.timeline.is_not(None)))
    ).all()
    for project_id, timeline in project_rows:
        if project_id in version_project_ids:
            continue
        timeline_refs += _timeline_asset_references(timeline, asset.id)
    for _, timeline in version_rows:
        timeline_refs += _timeline_asset_references(timeline, asset.id)

    active_jobs = 0
    jobs = (
        await db.execute(
            select(Job).where(
                Job.project_id == asset.project_id,
                Job.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
    ).scalars().all()
    for job in jobs:
        if str((job.payload or {}).get("asset_id") or "") == asset.id:
            active_jobs += 1

    counts = {
        "timeline_references": timeline_refs,
        "script_unit_references": unit_refs,
        "shot_references": shot_refs,
        "candidate_references": candidate_refs,
        "project_media_references": media_refs,
        "active_jobs": active_jobs,
        "clips": len(clip_ids),
    }
    blockers: list[str] = []
    if timeline_refs:
        blockers.append(f"仍被 {timeline_refs} 个时间线片段使用")
    script_refs = unit_refs + shot_refs + candidate_refs
    if script_refs:
        blockers.append(f"仍被 {script_refs} 个脚本分镜或候选镜头引用")
    if media_refs:
        blockers.append(f"仍被 {media_refs} 个项目素材箱引用")
    if active_jobs:
        blockers.append(f"仍有 {active_jobs} 个相关任务未结束")
    return {
        "entity_type": "asset",
        "entity_id": asset.id,
        "name": asset.name,
        "can_delete": not blockers,
        "blockers": blockers,
        "counts": counts,
    }


async def script_delete_impact(db: AsyncSession, script: Script) -> dict[str, Any]:
    linked_projects = int(
        (await db.execute(select(func.count()).where(Project.source_script_id == script.id))).scalar()
        or 0
    )
    snapshots = int(
        (await db.execute(select(func.count()).where(Script.parent_script_id == script.id))).scalar()
        or 0
    )
    media_refs = int(
        (
            await db.execute(
                select(func.count()).where(ProjectMediaItem.source_script_id == script.id)
            )
        ).scalar()
        or 0
    )
    active_jobs = 0
    jobs = (
        await db.execute(
            select(Job).where(
                Job.status.in_(ACTIVE_JOB_STATUSES),
                Job.project_id == script.project_id,
            )
        )
    ).scalars().all()
    for job in jobs:
        if str((job.payload or {}).get("script_id") or "") == script.id:
            active_jobs += 1

    unit_count = int(
        (await db.execute(select(func.count()).where(ScriptUnit.script_id == script.id))).scalar()
        or 0
    )
    counts = {
        "linked_projects": linked_projects,
        "snapshots": snapshots,
        "project_media_references": media_refs,
        "active_jobs": active_jobs,
        "units": unit_count,
    }
    blockers: list[str] = []
    if linked_projects:
        blockers.append(f"已生成 {linked_projects} 个剪辑项目")
    if snapshots:
        blockers.append(f"仍有 {snapshots} 个初剪快照依赖该脚本")
    if media_refs:
        blockers.append(f"仍被 {media_refs} 个项目素材箱引用")
    if active_jobs:
        blockers.append(f"仍有 {active_jobs} 个相关任务未结束")
    return {
        "entity_type": "script",
        "entity_id": script.id,
        "name": script.title,
        "can_delete": not blockers,
        "blockers": blockers,
        "counts": counts,
    }


async def project_delete_impact(db: AsyncSession, project: Project) -> dict[str, Any]:
    script_ids = list(
        (await db.execute(select(Script.id).where(Script.project_id == project.id))).scalars().all()
    )
    linked_projects = 0
    if script_ids:
        linked_projects = int(
            (
                await db.execute(
                    select(func.count()).where(
                        Project.source_script_id.in_(script_ids),
                        Project.id != project.id,
                    )
                )
            ).scalar()
            or 0
        )
    active_jobs = int(
        (
            await db.execute(
                select(func.count()).where(
                    Job.project_id == project.id,
                    Job.status.in_(ACTIVE_JOB_STATUSES),
                )
            )
        ).scalar()
        or 0
    )
    asset_count = int(
        (await db.execute(select(func.count()).where(Asset.project_id == project.id))).scalar()
        or 0
    )
    job_count = int(
        (await db.execute(select(func.count()).where(Job.project_id == project.id))).scalar()
        or 0
    )
    media_count = int(
        (
            await db.execute(
                select(func.count()).where(ProjectMediaItem.project_id == project.id)
            )
        ).scalar()
        or 0
    )
    asset_ids = list(
        (await db.execute(select(Asset.id).where(Asset.project_id == project.id))).scalars().all()
    )
    external_asset_references = 0
    if asset_ids:
        clip_ids = list(
            (await db.execute(select(Clip.id).where(Clip.asset_id.in_(asset_ids)))).scalars().all()
        )
        if clip_ids:
            external_asset_references += int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(ScriptUnit)
                        .join(Script, Script.id == ScriptUnit.script_id)
                        .where(
                            Script.project_id != project.id,
                            ScriptUnit.selected_clip_id.in_(clip_ids),
                        )
                    )
                ).scalar()
                or 0
            )
            external_asset_references += int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(Shot)
                        .join(ScriptUnit, ScriptUnit.id == Shot.unit_id)
                        .join(Script, Script.id == ScriptUnit.script_id)
                        .where(
                            Script.project_id != project.id,
                            Shot.selected_clip_id.in_(clip_ids),
                        )
                    )
                ).scalar()
                or 0
            )
            all_candidate_ids = set(
                (
                    await db.execute(
                        select(Candidate.id).where(Candidate.clip_id.in_(clip_ids))
                    )
                ).scalars().all()
            )
            internal_unit_ids = set(
                (
                    await db.execute(
                        select(ScriptUnit.id).where(ScriptUnit.script_id.in_(script_ids))
                    )
                ).scalars().all()
            ) if script_ids else set()
            internal_shot_ids = set(
                (
                    await db.execute(
                        select(Shot.id).where(Shot.unit_id.in_(internal_unit_ids))
                    )
                ).scalars().all()
            ) if internal_unit_ids else set()
            internal_candidate_ids: set[str] = set()
            if internal_unit_ids:
                internal_candidate_ids.update(
                    (
                        await db.execute(
                            select(Candidate.id).where(Candidate.unit_id.in_(internal_unit_ids))
                        )
                    ).scalars().all()
                )
            if internal_shot_ids:
                internal_candidate_ids.update(
                    (
                        await db.execute(
                            select(Candidate.id).where(Candidate.shot_id.in_(internal_shot_ids))
                        )
                    ).scalars().all()
                )
            external_asset_references += len(all_candidate_ids - internal_candidate_ids)

        external_asset_references += int(
            (
                await db.execute(
                    select(func.count()).where(
                        ProjectMediaItem.project_id != project.id,
                        ProjectMediaItem.asset_id.in_(asset_ids),
                    )
                )
            ).scalar()
            or 0
        )
        external_version_rows = (
            await db.execute(
                select(CutVersion.project_id, CutVersion.timeline).where(
                    CutVersion.project_id != project.id
                )
            )
        ).all()
        version_project_ids = {project_id for project_id, _ in external_version_rows}
        project_rows = (
            await db.execute(
                select(Project.id, Project.timeline).where(
                    Project.id != project.id,
                    Project.timeline.is_not(None),
                )
            )
        ).all()
        for external_project_id, timeline in project_rows:
            if external_project_id in version_project_ids:
                continue
            for asset_id in asset_ids:
                external_asset_references += _timeline_asset_references(timeline, asset_id)
        for _, timeline in external_version_rows:
            for asset_id in asset_ids:
                external_asset_references += _timeline_asset_references(timeline, asset_id)
    counts = {
        "linked_projects": linked_projects,
        "active_jobs": active_jobs,
        "assets": asset_count,
        "scripts": len(script_ids),
        "jobs": job_count,
        "project_media_items": media_count,
        "external_asset_references": external_asset_references,
    }
    blockers: list[str] = []
    if linked_projects:
        blockers.append(f"项目内脚本已被 {linked_projects} 个其他剪辑项目使用")
    if active_jobs:
        blockers.append(f"仍有 {active_jobs} 个任务未结束，请先取消或等待完成")
    if external_asset_references:
        blockers.append(f"项目素材仍被外部脚本或时间线引用 {external_asset_references} 次")
    return {
        "entity_type": "project",
        "entity_id": project.id,
        "name": project.name,
        "can_delete": not blockers,
        "blockers": blockers,
        "counts": counts,
    }


async def project_storage_paths(db: AsyncSession, project_id: str) -> set[str]:
    """收集项目独占文件；共享 AI 文件会在仍有媒体索引引用时保留。"""
    paths: set[str] = set()
    assets = (
        await db.execute(select(Asset).where(Asset.project_id == project_id))
    ).scalars().all()
    asset_ids = [asset.id for asset in assets]
    for asset in assets:
        paths.update(
            path for path in (asset.file_path, asset.preview_path, asset.thumbnail_path) if path
        )
    if asset_ids:
        paths.update(
            path
            for path in (
                await db.execute(
                    select(Clip.thumbnail_path).where(
                        Clip.asset_id.in_(asset_ids), Clip.thumbnail_path.is_not(None)
                    )
                )
            ).scalars().all()
            if path
        )

    script_ids = list(
        (await db.execute(select(Script.id).where(Script.project_id == project_id))).scalars().all()
    )
    if script_ids:
        generated_rows = (
            await db.execute(
                select(
                    Shot.generated_image_path,
                    Shot.generated_video_path,
                    Shot.generated_effect_video_path,
                )
                .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
                .where(ScriptUnit.script_id.in_(script_ids))
            )
        ).all()
        for row in generated_rows:
            paths.update(path for path in row if path)
        paths.update(
            path
            for path in (
                await db.execute(
                    select(ShotGeneration.storage_path)
                    .join(Shot, Shot.id == ShotGeneration.shot_id)
                    .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
                    .where(ScriptUnit.script_id.in_(script_ids))
                )
            ).scalars().all()
            if path
        )
    paths.update(
        path
        for path in (
            await db.execute(
                select(Job.result_path).where(
                    Job.project_id == project_id, Job.result_path.is_not(None)
                )
            )
        ).scalars().all()
        if path
    )
    project_version_timelines = (
        await db.execute(
            select(CutVersion.timeline).where(CutVersion.project_id == project_id)
        )
    ).scalars().all()
    for timeline in project_version_timelines:
        for item in timeline or []:
            path = item.get("generated_media_path")
            if path:
                paths.add(path)

    shared_paths = (
        set(
            (
                await db.execute(
                    select(ProjectMediaItem.storage_path).where(
                        ProjectMediaItem.project_id != project_id,
                        ProjectMediaItem.storage_path.in_(paths),
                    )
                )
            ).scalars().all()
        )
        if paths
        else set()
    )
    if paths:
        external_asset_rows = (
            await db.execute(
                select(Asset.file_path, Asset.preview_path, Asset.thumbnail_path).where(
                    Asset.project_id != project_id,
                    or_(
                        Asset.file_path.in_(paths),
                        Asset.preview_path.in_(paths),
                        Asset.thumbnail_path.in_(paths),
                    ),
                )
            )
        ).all()
        for row in external_asset_rows:
            shared_paths.update(path for path in row if path in paths)
        shared_paths.update(
            path
            for path in (
                await db.execute(
                    select(Clip.thumbnail_path)
                    .join(Asset)
                    .where(
                        Asset.project_id != project_id,
                        Clip.thumbnail_path.in_(paths),
                    )
                )
            ).scalars().all()
            if path
        )
        shared_paths.update(
            path
            for path in (
                await db.execute(
                    select(ShotGeneration.storage_path)
                    .join(Shot, Shot.id == ShotGeneration.shot_id)
                    .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
                    .join(Script, Script.id == ScriptUnit.script_id)
                    .where(
                        Script.project_id != project_id,
                        ShotGeneration.storage_path.in_(paths),
                    )
                )
            ).scalars().all()
            if path
        )
        external_generated_rows = (
            await db.execute(
                select(
                    Shot.generated_image_path,
                    Shot.generated_video_path,
                    Shot.generated_effect_video_path,
                )
                .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
                .join(Script, Script.id == ScriptUnit.script_id)
                .where(
                    Script.project_id != project_id,
                    or_(
                        Shot.generated_image_path.in_(paths),
                        Shot.generated_video_path.in_(paths),
                        Shot.generated_effect_video_path.in_(paths),
                    ),
                )
            )
        ).all()
        for row in external_generated_rows:
            shared_paths.update(path for path in row if path in paths)

        external_timelines = (
            await db.execute(
                select(Project.timeline).where(
                    Project.id != project_id,
                    Project.timeline.is_not(None),
                )
            )
        ).scalars().all()
        for timeline in external_timelines:
            for item in timeline or []:
                path = item.get("generated_media_path")
                if path in paths:
                    shared_paths.add(path)
        external_version_timelines = (
            await db.execute(
                select(CutVersion.timeline).where(CutVersion.project_id != project_id)
            )
        ).scalars().all()
        for timeline in external_version_timelines:
            for item in timeline or []:
                path = item.get("generated_media_path")
                if path in paths:
                    shared_paths.add(path)
    return paths - shared_paths
