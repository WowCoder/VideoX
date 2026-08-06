"""剪辑时间线的统一业务校验。

保存接口、导出接口和后台渲染任务必须使用同一套规则，避免时间线在编辑器中
看似合法，却在保存或导出阶段才失败。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, Clip
from app.models.project import Project
from app.models.script import Script
from app.models.user import User
from app.services.project_access import require_project_access


TIMELINE_EPSILON = 0.05


class TimelineValidationError(ValueError):
    """包含可直接展示给用户的时间线问题。"""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(issues[0] if len(issues) == 1 else f"{issues[0]}（另有 {len(issues) - 1} 个问题）")


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_timeline_layout(
    clips: Iterable[Any],
    assets_by_id: dict[str, Asset],
    source_clips_by_id: dict[str, Clip] | None = None,
    *,
    allow_placeholders: bool = False,
) -> list[str]:
    """校验片段范围、来源片段和当前单视频轨布局。"""
    issues: list[str] = []
    video_clips: list[Any] = []
    source_clips_by_id = source_clips_by_id or {}

    for item in clips:
        name = str(_value(item, "name", "未命名片段"))
        track = _value(item, "track")
        asset_id = _value(item, "asset_id")
        source_clip_id = _value(item, "source_clip_id")
        origin = _value(item, "origin")
        generated_media_path = _value(item, "generated_media_path")
        generated_media_type = _value(item, "generated_media_type")
        start = _number(_value(item, "start"))
        duration = _number(_value(item, "duration"))
        source_start = _number(_value(item, "source_start"))

        if track == "video":
            video_clips.append(item)
            if not asset_id:
                if origin == "script_placeholder":
                    if not allow_placeholders:
                        issues.append(f"分镜「{name}」仍是待补素材占位片段")
                elif origin in {"script_generated", "manual_generated"}:
                    if not generated_media_path or generated_media_type not in {"image", "video"}:
                        issues.append(f"AI 生成片段「{name}」缺少可用媒体")
                else:
                    issues.append(f"视频片段「{name}」没有关联真实素材")

        if not asset_id:
            continue

        asset = assets_by_id.get(str(asset_id))
        if not asset:
            issues.append(f"片段「{name}」引用的素材不存在或不可访问")
            continue

        if track == "video" and getattr(asset, "media_type", "video") != "video":
            issues.append(f"视频片段「{name}」引用的是音频素材")
        if track == "audio" and not getattr(asset, "has_audio", True):
            issues.append(f"音频片段「{name}」引用的素材没有可用音轨")

        if source_clip_id:
            source_clip = source_clips_by_id.get(str(source_clip_id))
            if not source_clip or source_clip.asset_id != asset.id:
                issues.append(f"片段「{name}」引用的识别片段与源素材不匹配")
            elif (
                source_start < source_clip.start_time - TIMELINE_EPSILON
                or source_start + duration > source_clip.end_time + TIMELINE_EPSILON
            ):
                issues.append(f"片段「{name}」超出所选识别片段的入点或出点")

        if source_start < 0 or duration <= 0 or start < 0:
            issues.append(f"片段「{name}」的时间范围无效")
        elif asset.duration > 0 and source_start + duration > asset.duration + TIMELINE_EPSILON:
            issues.append(f"片段「{name}」超出源素材时长，请缩短片段")

    cursor = 0.0
    for item in sorted(video_clips, key=lambda clip: _number(_value(clip, "start"))):
        start = _number(_value(item, "start"))
        duration = _number(_value(item, "duration"))
        if start < cursor - 0.01:
            issues.append(f"视频片段「{_value(item, 'name', '未命名片段')}」与前一个片段重叠")
        cursor = max(cursor, start + duration)

    return issues


async def validate_project_timeline(
    project: Project,
    clips: Iterable[Any],
    db: AsyncSession,
    user: User | None = None,
    *,
    allow_placeholders: bool = False,
) -> dict[str, Asset]:
    """校验素材来源权限及时间线业务约束，并返回涉及的素材。"""
    clip_items = list(clips)
    allowed_project_ids = {project.id}

    if project.source_script_id:
        source_project_id = (
            await db.execute(
                select(Script.project_id).where(Script.id == project.source_script_id)
            )
        ).scalar_one_or_none()
        if source_project_id:
            if user:
                await require_project_access(source_project_id, user, db)
            allowed_project_ids.add(source_project_id)

    asset_ids = {
        str(_value(item, "asset_id"))
        for item in clip_items
        if _value(item, "asset_id")
    }
    assets = (
        (
            await db.execute(
                select(Asset).where(
                    Asset.id.in_(asset_ids),
                    Asset.project_id.in_(allowed_project_ids),
                )
            )
        ).scalars().all()
        if asset_ids
        else []
    )
    assets_by_id = {asset.id: asset for asset in assets}

    source_clip_ids = {
        str(_value(item, "source_clip_id"))
        for item in clip_items
        if _value(item, "source_clip_id")
    }
    source_clips = (
        (
            await db.execute(select(Clip).where(Clip.id.in_(source_clip_ids)))
        ).scalars().all()
        if source_clip_ids
        else []
    )
    source_clips_by_id = {clip.id: clip for clip in source_clips}

    issues = validate_timeline_layout(
        clip_items,
        assets_by_id,
        source_clips_by_id,
        allow_placeholders=allow_placeholders,
    )
    if issues:
        raise TimelineValidationError(issues)
    return assets_by_id
