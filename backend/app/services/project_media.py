"""把脚本和时间线引用同步到项目素材箱索引。"""

from __future__ import annotations

from sqlalchemy import select

from app.models.asset import Asset
from app.models.project import Project
from app.models.project_media import ProjectMediaItem
from app.models.script import Script


def generated_kind(path: str, media_type: str) -> str:
    if "/effects/" in path:
        return "ai_effect_video"
    return "ai_video" if media_type == "video" else "ai_image"


async def _upsert(session, project_id: str, dedupe_key: str, **values) -> ProjectMediaItem:
    item = (
        await session.execute(
            select(ProjectMediaItem).where(
                ProjectMediaItem.project_id == project_id,
                ProjectMediaItem.dedupe_key == dedupe_key,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = ProjectMediaItem(project_id=project_id, dedupe_key=dedupe_key, **values)
        session.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)
    return item


async def sync_project_media_items(
    session,
    project: Project,
    snapshot_script: Script | None = None,
) -> list[ProjectMediaItem]:
    """同步项目当前时间线和脚本快照引用；不复制或删除底层对象。"""
    source_project_id = None
    if project.source_script_id:
        source_project_id = (
            await session.execute(
                select(Script.project_id).where(Script.id == project.source_script_id)
            )
        ).scalar_one_or_none()

    for clip in project.timeline or []:
        asset_id = clip.get("asset_id")
        if asset_id:
            asset = await session.get(Asset, str(asset_id))
            if asset:
                await _upsert(
                    session,
                    project.id,
                    f"asset:{asset.id}",
                    kind="source_asset",
                    asset_id=asset.id,
                    storage_path=None,
                    media_type=asset.media_type or "video",
                    source_project_id=asset.project_id,
                    source_script_id=clip.get("source_script_id") or project.source_script_id,
                    source_shot_id=clip.get("source_shot_id"),
                    name=asset.name,
                    duration=float(asset.duration or 0),
                    thumbnail_path=asset.thumbnail_path,
                )

        path = clip.get("generated_media_path")
        if path:
            media_type = clip.get("generated_media_type") or "video"
            await _upsert(
                session,
                project.id,
                f"storage:{path}",
                kind=generated_kind(str(path), media_type),
                asset_id=None,
                storage_path=str(path),
                media_type=media_type,
                source_project_id=source_project_id,
                source_script_id=clip.get("source_script_id") or project.source_script_id,
                source_shot_id=clip.get("source_shot_id"),
                name=clip.get("name") or "AI 生成媒体",
                duration=float(clip.get("duration") or 0),
                thumbnail_path=str(path) if media_type == "image" else None,
            )

    if snapshot_script:
        for unit in snapshot_script.units or []:
            for shot in unit.shots or []:
                generated = (
                    (shot.generated_image_path, "ai_image", "image"),
                    (shot.generated_video_path, "ai_video", "video"),
                    (shot.generated_effect_video_path, "ai_effect_video", "video"),
                )
                for path, kind, media_type in generated:
                    if not path:
                        continue
                    await _upsert(
                        session,
                        project.id,
                        f"storage:{path}",
                        kind=kind,
                        asset_id=None,
                        storage_path=path,
                        media_type=media_type,
                        source_project_id=source_project_id,
                        source_script_id=project.source_script_id,
                        source_shot_id=shot.source_shot_id,
                        name=shot.description or "AI 生成媒体",
                        duration=float(shot.duration or 0),
                        thumbnail_path=path if media_type == "image" else None,
                    )

    await session.flush()
    return (
        await session.execute(
            select(ProjectMediaItem)
            .where(ProjectMediaItem.project_id == project.id)
            .order_by(ProjectMediaItem.created_at)
        )
    ).scalars().all()
