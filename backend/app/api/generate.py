"""显式作用范围的 AI、匹配、主成片编译和导出操作。"""

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset
from app.models.job import Job, VideoGenerationBatch
from app.models.project import Project
from app.models.script import ScriptUnit, Shot
from app.models.user import User
from app.models.voice import VoiceLine
from app.schemas.job import JobOut, VideoGenerationBatchOut
from app.schemas.project import ScopeSelection
from app.services.project_access import require_project_access
from app.services.quotas import QuotaExceededError, admit_job_quota
from app.services.billing_v2 import (
    active_catalog,
    active_plan_for_user,
    create_usage_quote,
    capture_hold,
    ensure_user_billing_account,
    reserve_credits,
    release_hold,
    quote_lines,
    wallet_balance,
    validate_plan_generation_entitlements,
)
from app.services.quotas import fail_job
from app.services.task_dispatch import dispatch_project_task
from app.services.workspace import load_project_workspace, record_revision


router = APIRouter()
settings = get_settings()


class CreationPreviewShot(BaseModel):
    description: str
    duration_ms: int = Field(..., ge=100)
    asset_id: str | None = None
    segment_id: str | None = None
    source_start_ms: int = Field(0, ge=0)
    source_end_ms: int = Field(0, ge=0)


class CreationPreviewScene(BaseModel):
    title: str
    narration: str
    visual: str
    duration_ms: int = Field(..., ge=100)
    shots: list[CreationPreviewShot]


class CreationPreviewOut(BaseModel):
    title: str
    summary: str
    scenes: list[CreationPreviewScene]


class OperationEstimateLineOut(BaseModel):
    sku: str
    unit: str
    quantity: int
    unit_credits: int
    credits: int


class OperationEstimateOut(BaseModel):
    estimate_id: str | None
    catalog_version_id: str | None
    estimated_credits: int
    available_credits: int
    remaining_after: int
    sufficient: bool
    expires_at: datetime | None
    lines: list[OperationEstimateLineOut]


class ScriptCreationPreviewRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=2000)
    duration_seconds: int = Field(60, ge=15, le=300)
    tone: str = Field("专业克制", min_length=1, max_length=50)
    pricing_catalog_id: str | None = Field(None, max_length=64)


class AssetCreationPreviewRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1, max_length=50)
    brief: str = Field("", max_length=2000)
    pricing_catalog_id: str | None = Field(None, max_length=64)


async def _validate_pricing_catalog(db: AsyncSession, catalog_id: str | None) -> None:
    if not settings.billing_v2_enabled or not catalog_id:
        return
    catalog = await active_catalog(db)
    if catalog is None or catalog.id != catalog_id:
        raise HTTPException(status_code=409, detail="V-Credits 价格已更新，请重新确认本次费用")


class CreationPreviewEstimateRequest(BaseModel):
    source: Literal["ai-script", "upload-assets"]


@router.post("/creation-previews/estimate", response_model=OperationEstimateOut)
async def estimate_creation_preview(
    request: CreationPreviewEstimateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await ensure_user_billing_account(db, user, for_update=True)
    balance = await wallet_balance(db, account)
    sku = "script.standard" if request.source == "ai-script" else "storyboard.standard"
    try:
        quote = await create_usage_quote(
            db,
            account,
            [{"sku": sku, "quantity": 1, "metadata": {"operation": "creation_preview"}}],
            request_snapshot={"source": request.source},
        )
        quoted_lines = await quote_lines(db, quote.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    available = balance["available_credits"]
    return OperationEstimateOut(
        estimate_id=quote.id,
        catalog_version_id=quote.catalog_version_id,
        estimated_credits=quote.total_credits,
        available_credits=available,
        remaining_after=max(0, available - quote.total_credits),
        sufficient=available >= quote.total_credits,
        expires_at=quote.expires_at,
        lines=[OperationEstimateLineOut(sku=line.sku, unit=line.unit, quantity=line.quantity, unit_credits=line.unit_credits, credits=line.credits) for line in quoted_lines],
    )


async def _reserve_preview_credits(
    db: AsyncSession,
    user: User,
    *,
    sku: str,
    operation: str,
    request_snapshot: dict,
) -> str | None:
    if not settings.billing_v2_enabled:
        return None
    account = await ensure_user_billing_account(db, user, for_update=True)
    quote = await create_usage_quote(
        db,
        account,
        [{"sku": sku, "quantity": 1, "metadata": {"operation": operation}}],
        request_snapshot=request_snapshot,
    )
    hold = await reserve_credits(
        db,
        account,
        quote.total_credits,
        idempotency_key=f"preview:{user.id}:{uuid.uuid4().hex}",
        quote_id=quote.id,
        reason=f"{operation}积分预占",
    )
    await db.commit()
    return hold.id


def _asset_preview_context(assets: list[Asset]) -> tuple[list[dict], dict[str, dict]]:
    """Build model context, including legacy ready assets without segment rows."""
    asset_context: list[dict] = []
    available_segments: dict[str, dict] = {}
    for asset in assets:
        segments = sorted(asset.segments, key=lambda item: (item.start_ms, item.id))
        if not segments:
            # Older/imported assets can legitimately be ready while having no
            # normalized segment rows.  Give the model a stable request-only
            # reference and later return segment_id=None so workspace saving
            # links the whole asset instead of inventing a database segment.
            segments = [None]
        for segment in segments:
            recognition = (segment.recognition if segment else asset.recognition) or {}
            summary = str(recognition.get("summary") or "").strip()
            eligible_as_visual = asset.media_type in {"image", "video"}
            reference_id = segment.id if segment else f"whole-asset:{asset.id}"
            start_ms = segment.start_ms if segment else 0
            end_ms = segment.end_ms if segment else max(0, asset.duration_ms or 0)
            title = segment.title if segment else asset.name
            if eligible_as_visual:
                available_segments[reference_id] = {
                    "asset_id": asset.id,
                    "segment_id": segment.id if segment else None,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "title": title,
                    "summary": summary,
                }
            asset_context.append({
                "asset_id": asset.id,
                "asset_name": asset.name,
                "media_type": asset.media_type,
                "eligible_as_visual": eligible_as_visual,
                "segment_id": reference_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "title": title,
                "summary": summary,
                "transcript": ((segment.transcript if segment else asset.transcript) or "")[:1200],
                "ocr": ((segment.ocr_text if segment else asset.ocr_text) or "")[:600],
                "tags": ((segment.tags if segment else asset.tags) or [])[:20],
                "recognition": {
                    key: recognition.get(key, [] if key not in {"shot", "quality"} else {})
                    for key in ("spaces", "people", "objects", "actions", "shot", "quality")
                },
                "quality_score": segment.quality_score if segment else 0,
            })
    return asset_context, available_segments


@router.post("/creation-previews/script", response_model=CreationPreviewOut)
async def create_script_preview(
    request: ScriptCreationPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _validate_pricing_catalog(db, request.pricing_catalog_id)
    if not settings.has_text_generation:
        raise HTTPException(status_code=503, detail="AI 脚本服务未配置，请先配置 DashScope 文本模型")
    from app.services.creation_preview import generate_script_preview

    try:
        hold_id = await _reserve_preview_credits(
            db,
            user,
            sku="script.standard",
            operation="脚本创建预览",
            request_snapshot=request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        result = await generate_script_preview(
            request.prompt.strip(), request.duration_seconds, request.tone.strip()
        )
        response = CreationPreviewOut.model_validate(result)
        if hold_id:
            await capture_hold(db, hold_id, reason="脚本创建预览成功结算")
            await db.commit()
    except Exception as exc:
        if hold_id:
            await release_hold(db, hold_id, reason="脚本创建预览失败释放")
            await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return response


@router.post("/creation-previews/assets", response_model=CreationPreviewOut)
async def create_asset_preview(
    request: AssetCreationPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _validate_pricing_catalog(db, request.pricing_catalog_id)
    if not settings.has_text_generation:
        raise HTTPException(status_code=503, detail="AI 编排服务未配置，请先配置 DashScope 文本模型")
    requested_ids = list(dict.fromkeys(request.asset_ids))
    assets = (
        await db.execute(
            select(Asset)
            .where(
                Asset.id.in_(requested_ids),
                Asset.owner_id == user.id,
                Asset.deleted_at.is_(None),
                Asset.processing_status == "ready",
            )
            .options(selectinload(Asset.segments))
        )
    ).scalars().all()
    if len(assets) != len(requested_ids):
        raise HTTPException(status_code=422, detail="部分素材不存在、尚未处理完成或无权访问")

    asset_context, available_segments = _asset_preview_context(assets)
    if not available_segments:
        raise HTTPException(status_code=422, detail="所选素材中没有可用于画面编排的图片或视频；音频只能作为叙事参考")

    from app.services.creation_preview import generate_asset_preview

    try:
        hold_id = await _reserve_preview_credits(
            db,
            user,
            sku="storyboard.standard",
            operation="素材创建预览",
            request_snapshot={"asset_ids": requested_ids, "brief": request.brief},
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        result = await generate_asset_preview(
            asset_context, available_segments, request.brief.strip()
        )
        response = CreationPreviewOut.model_validate(result)
        if hold_id:
            await capture_hold(db, hold_id, reason="素材创建预览成功结算")
            await db.commit()
    except Exception as exc:
        if hold_id:
            await release_hold(db, hold_id, reason="素材创建预览失败释放")
            await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return response


class ProjectOperationRequest(BaseModel):
    scope: ScopeSelection
    operation: Literal[
        "match_assets",
        "complete_shots",
        "generate_image",
        "generate_video",
        "generate_effect",
        "generate_script",
        "generate_voiceover",
        "compose",
        "export",
    ]
    parameters: dict = Field(default_factory=dict)
    expected_revision: int = Field(..., ge=0)
    pricing_catalog_id: str | None = Field(None, max_length=64)


class OperationJobsOut(BaseModel):
    jobs: list[JobOut]
    video_batch: VideoGenerationBatchOut | None = None


def _resolve_shot_ids(project: Project, scope: ScopeSelection) -> list[str]:
    scenes = project.script.units
    if scope.type == "project":
        return [shot.id for scene in scenes for shot in scene.shots]
    if scope.type == "scene":
        requested = set(scope.scene_ids)
        owned = {scene.id for scene in scenes}
        if not requested or not requested <= owned:
            raise HTTPException(status_code=422, detail="作用范围包含不属于当前项目的场景")
        return [shot.id for scene in scenes if scene.id in requested for shot in scene.shots]
    if scope.type == "shot":
        requested = set(scope.shot_ids)
        owned = {shot.id for scene in scenes for shot in scene.shots}
        if not requested or not requested <= owned:
            raise HTTPException(status_code=422, detail="作用范围包含不属于当前项目的镜头")
        return [shot.id for scene in scenes for shot in scene.shots if shot.id in requested]
    raise HTTPException(status_code=422, detail="该操作不支持素材级作用范围")


def _resolve_scene_ids(project: Project, scope: ScopeSelection) -> list[str]:
    scenes = project.script.units
    if scope.type == "project":
        return [scene.id for scene in scenes]
    if scope.type == "scene":
        requested = set(scope.scene_ids)
        owned = {scene.id for scene in scenes}
        if not requested or not requested <= owned:
            raise HTTPException(status_code=422, detail="作用范围包含不属于当前项目的场景")
        return [scene.id for scene in scenes if scene.id in requested]
    if scope.type == "shot":
        requested = set(scope.shot_ids)
        owned = {shot.id for scene in scenes for shot in scene.shots}
        if not requested or not requested <= owned:
            raise HTTPException(status_code=422, detail="作用范围包含不属于当前项目的镜头")
        return [scene.id for scene in scenes if any(shot.id in requested for shot in scene.shots)]
    raise HTTPException(status_code=422, detail="AI 配音不支持素材级作用范围")


def _generation_prompt(shot: Shot, parameters: dict, prompt_key: str) -> str:
    """为批量生成逐镜头组装提示词，避免用同一段画面描述覆盖所有镜头。"""
    use_shot_descriptions = bool(parameters.get("use_shot_descriptions"))
    if use_shot_descriptions:
        base = (shot.description or shot.unit.intent or shot.unit.narration_text or "").strip()
    else:
        base = str(parameters.get(prompt_key) or "").strip()
    additional = str(parameters.get("additional_instruction") or "").strip()
    style = str(parameters.get("style") or "").strip()
    parts = [base]
    if additional:
        parts.append(f"全局补充要求：{additional}")
    if style:
        parts.append(f"视觉风格：{style}")
    return "。".join(part.rstrip("。") for part in parts if part) + ("。" if any(parts) else "")


def _validated_video_generation(
    project: Project,
    user_id: str,
    scope: ScopeSelection,
    shot_ids: list[str],
    parameters: dict,
) -> dict:
    """校验 Flash 媒体输入，并保存可审计、不可变的素材来源。"""
    mode = str(parameters.get("generation_mode") or "text").strip().lower()
    if mode not in {"text", "keyframe", "reference"}:
        raise HTTPException(status_code=422, detail="视频生成模式无效")
    if mode != "text" and (scope.type != "shot" or len(shot_ids) != 1):
        raise HTTPException(status_code=422, detail="关键帧和图片参考模式暂时只支持单个镜头")
    try:
        duration_seconds = int(parameters.get("duration_seconds") or 5)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="视频时长必须是整数秒") from exc
    if not 4 <= duration_seconds <= 12:
        raise HTTPException(status_code=422, detail="Agnes Video 2.5 Flash 时长需为 4–12 秒")

    first_frame_id = str(parameters.get("first_frame_asset_id") or "").strip()
    last_frame_id = str(parameters.get("last_frame_asset_id") or "").strip()
    raw_reference_ids = parameters.get("reference_image_asset_ids") or []
    if not isinstance(raw_reference_ids, list):
        raise HTTPException(status_code=422, detail="参考图片参数格式无效")
    reference_ids = list(dict.fromkeys(str(item).strip() for item in raw_reference_ids if str(item).strip()))
    if len(reference_ids) > 5:
        raise HTTPException(status_code=422, detail="Agnes Video 2.5 Flash 最多支持 5 张参考图片")
    if mode == "text" and (first_frame_id or last_frame_id or reference_ids):
        raise HTTPException(status_code=422, detail="文生视频模式不能携带参考图片")
    if mode == "keyframe" and not (first_frame_id or last_frame_id):
        raise HTTPException(status_code=422, detail="关键帧模式至少需要首帧或尾帧")
    if mode == "reference" and not reference_ids:
        raise HTTPException(status_code=422, detail="图片参考模式至少需要一张参考图片")
    if mode == "keyframe" and reference_ids:
        raise HTTPException(status_code=422, detail="关键帧模式不能同时使用参考图片列表")
    if mode == "reference" and (first_frame_id or last_frame_id):
        raise HTTPException(status_code=422, detail="图片参考模式不能同时设置首尾帧")

    linked_assets = {
        link.asset.id: link.asset
        for link in project.asset_links
        if link.asset is not None
    }
    requested_ids = list(dict.fromkeys(
        asset_id for asset_id in [first_frame_id, last_frame_id, *reference_ids] if asset_id
    ))
    for asset_id in requested_ids:
        asset = linked_assets.get(asset_id)
        if (
            not asset
            or asset.owner_id != user_id
            or asset.deleted_at is not None
            or asset.status != "ready"
            or asset.processing_status != "ready"
            or asset.media_type != "image"
            or not asset.file_path
        ):
            raise HTTPException(status_code=422, detail="部分参考素材不可用；请选择当前项目中处理完成的图片")

    reference_assets = []
    if first_frame_id:
        reference_assets.append({"asset_id": first_frame_id, "role": "first_frame", "ordinal": 1})
    if last_frame_id:
        reference_assets.append({"asset_id": last_frame_id, "role": "last_frame", "ordinal": 1})
    reference_assets.extend(
        {"asset_id": asset_id, "role": "reference", "ordinal": index + 1}
        for index, asset_id in enumerate(reference_ids)
    )
    return {
        "provider": "agnes",
        "model": settings.agnes_video_model,
        "mode": mode,
        "duration_seconds": duration_seconds,
        "reference_assets": reference_assets,
    }


def _media_billing_sku(operation: str, parameters: dict, video_generation: dict | None) -> tuple[str, int]:
    """把前端媒体参数映射到可由后台调整的 SKU 和计费数量。"""
    if operation == "generate_image":
        resolution = str(parameters.get("resolution") or "1k").strip().lower()
        quality = str(parameters.get("quality") or parameters.get("tier") or "").strip().lower()
        if "pro" in quality and resolution in {"4k", "4k2", "2k"}:
            return ("image.pro.4k" if resolution == "4k" else "image.pro.2k", 1)
        if resolution in {"4k", "2k"}:
            return "image.standard.2k", 1
        return "image.fast.1k", 1
    if operation == "generate_effect":
        try:
            duration = int(parameters.get("duration_seconds") or 5)
        except (TypeError, ValueError):
            duration = 5
        return "video.standard.720p", max(1, duration)
    video_generation = video_generation or {}
    try:
        duration = max(1, int(video_generation.get("duration_seconds") or parameters.get("duration_seconds") or 5))
    except (TypeError, ValueError):
        duration = 5
    resolution = str(parameters.get("resolution") or "720p").strip().lower()
    quality = str(parameters.get("quality") or parameters.get("tier") or parameters.get("model") or "").lower()
    if "premium" in quality or "pro" in quality:
        return ("video.premium.2k" if resolution in {"2k", "4k"} else "video.premium.1080p", duration)
    return ("video.standard.1080p" if resolution in {"1080p", "fhd"} else "video.standard.720p", duration)


def _operation_billing_sku(
    operation: str,
    project: Project,
    scene_ids: list[str],
    parameters: dict | None = None,
) -> tuple[str, int] | None:
    """Return the catalog SKU for non-media AI operations.

    The model-point sheet prices script/storyboard as one request and TTS by
    output minutes.  Quantity is deliberately calculated before dispatch so a
    failed provider call can release one complete reservation atomically.
    """
    if operation == "generate_script":
        return "script.standard", 1
    if operation == "complete_shots":
        return "storyboard.standard", 1
    if operation == "generate_voiceover":
        from app.services.tts.planning import build_voice_plans

        plans = build_voice_plans(project, set(scene_ids), "effective_subtitles")
        total_ms = sum(max(1, int(plan.get("target_duration_ms") or 0)) for plan in plans)
        if total_ms <= 0:
            return None
        model = str((parameters or {}).get("model") or "").strip().lower()
        sku = "tts.pro" if model.startswith("qwen-audio-") or "pro" in model else "tts.standard"
        return sku, max(1, math.ceil(total_ms / 60000))
    return None


async def _dispatch_job(db: AsyncSession, project: Project, job: Job):
    if job.type == "镜头匹配":
        from app.tasks.match_tasks import match_script_shots

        return await dispatch_project_task(
            db,
            project.id,
            match_script_shots,
            project.script.id,
            job.payload["shot_ids"],
            job.id,
        )
    if job.type == "AI 分镜完善":
        from app.tasks.script_tasks import complete_shot_descriptions

        return await dispatch_project_task(
            db,
            project.id,
            complete_shot_descriptions,
            project.script.id,
            job.payload["shot_ids"],
            job.id,
        )
    if job.type == "AI 脚本生成":
        from app.tasks.script_tasks import generate_project_script

        return await dispatch_project_task(
            db,
            project.id,
            generate_project_script,
            project.id,
            job.id,
        )
    if job.type == "AI 生图分镜":
        from app.tasks.generate_tasks import generate_image_shot

        return await dispatch_project_task(
            db,
            project.id,
            generate_image_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("prompt", ""),
        )
    if job.type == "分镜图 AI 生视频":
        from app.tasks.generate_tasks import generate_video_shot

        return await dispatch_project_task(
            db,
            project.id,
            generate_video_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("prompt", ""),
        )
    if job.type == "示意图特效视频":
        from app.tasks.generate_tasks import generate_effect_shot

        return await dispatch_project_task(
            db,
            project.id,
            generate_effect_shot,
            job.payload["shot_id"],
            job.id,
            job.payload.get("motion_description", ""),
        )
    if job.type == "AI 初剪生成":
        from app.tasks.roughcut_tasks import run_rough_cut

        return await dispatch_project_task(
            db, project.id, run_rough_cut, job.id, project.id
        )
    if job.type == "AI 配音生成":
        from app.tasks.voice_tasks import generate_project_voiceover

        return await dispatch_project_task(
            db, project.id, generate_project_voiceover, job.id, project.id
        )
    if job.type == "导出":
        from app.tasks.export_tasks import export_project

        return await dispatch_project_task(
            db,
            project.id,
            export_project,
            project.id,
            job.id,
            job.payload.get("format", "mp4"),
            job.payload.get("resolution", "1080p"),
            job.payload.get("aspect_ratio"),
        )
    raise HTTPException(status_code=422, detail="不支持该任务类型")


@router.post(
    "/projects/{project_id}/operations/estimate",
    response_model=OperationEstimateOut,
)
async def estimate_project_operation(
    project_id: str,
    request: ProjectOperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Price a user operation with the same server-side SKU mapping as execution."""
    await require_project_access(project_id, user, db, "viewer")
    project = await load_project_workspace(db, project_id, user.id)
    if project.script.revision != request.expected_revision:
        raise HTTPException(status_code=409, detail="项目版本已变化，请刷新后重新确认费用")
    if not settings.billing_v2_enabled:
        return OperationEstimateOut(
            estimate_id=None, catalog_version_id=None, estimated_credits=0,
            available_credits=0, remaining_after=0, sufficient=True,
            expires_at=None, lines=[],
        )

    shot_ids = (
        _resolve_shot_ids(project, request.scope)
        if request.operation not in {"compose", "export", "generate_script", "generate_voiceover"}
        else []
    )
    scene_ids = (
        _resolve_scene_ids(project, request.scope)
        if request.operation == "generate_voiceover"
        else []
    )
    spec: tuple[str, int] | None = None
    if request.operation in {"generate_image", "generate_video", "generate_effect"}:
        video_generation = (
            _validated_video_generation(project, user.id, request.scope, shot_ids, request.parameters)
            if request.operation == "generate_video"
            else None
        )
        sku, quantity = _media_billing_sku(request.operation, request.parameters, video_generation)
        plan = await active_plan_for_user(db, user)
        try:
            validate_plan_generation_entitlements(
                plan,
                operation="image" if request.operation == "generate_image" else "video",
                resolution=str(request.parameters.get("resolution") or ""),
                batch=len(shot_ids) > 1,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        spec = sku, quantity * len(shot_ids)
    else:
        spec = _operation_billing_sku(
            request.operation,
            project,
            scene_ids,
            request.parameters,
        )
        if request.operation == "generate_voiceover" and request.parameters.get("voice_line_ids"):
            raw_line_ids = request.parameters["voice_line_ids"]
            if not isinstance(raw_line_ids, list):
                raise HTTPException(status_code=422, detail="配音段参数格式无效")
            requested_line_ids = list(dict.fromkeys(str(item) for item in raw_line_ids))
            durations = (
                await db.execute(
                    select(VoiceLine.target_duration_ms).where(
                        VoiceLine.project_id == project_id,
                        VoiceLine.id.in_(requested_line_ids),
                    )
                )
            ).scalars().all()
            if len(durations) != len(requested_line_ids):
                raise HTTPException(status_code=422, detail="部分配音段不存在或不属于当前项目")
            model = str(request.parameters.get("model") or "").lower()
            sku = "tts.pro" if model.startswith("qwen-audio-") or "pro" in model else "tts.standard"
            spec = sku, max(1, math.ceil(sum(max(1, int(value)) for value in durations) / 60000))

    account = await ensure_user_billing_account(db, user, for_update=True)
    balance = await wallet_balance(db, account)
    if spec is None:
        catalog = await active_catalog(db)
        return OperationEstimateOut(
            estimate_id=None,
            catalog_version_id=catalog.id if catalog else None,
            estimated_credits=0,
            available_credits=balance["available_credits"],
            remaining_after=balance["available_credits"],
            sufficient=True,
            expires_at=None,
            lines=[],
        )
    sku, quantity = spec
    try:
        quote = await create_usage_quote(
            db,
            account,
            [{"sku": sku, "quantity": quantity, "metadata": {"operation": request.operation}}],
            request_snapshot={
                "operation": request.operation,
                "project_id": project_id,
                "scope": request.scope.model_dump(),
                "parameters": request.parameters,
                "expected_revision": request.expected_revision,
            },
        )
        quoted_lines = await quote_lines(db, quote.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    available = balance["available_credits"]
    return OperationEstimateOut(
        estimate_id=quote.id,
        catalog_version_id=quote.catalog_version_id,
        estimated_credits=quote.total_credits,
        available_credits=available,
        remaining_after=max(0, available - quote.total_credits),
        sufficient=available >= quote.total_credits,
        expires_at=quote.expires_at,
        lines=[
            OperationEstimateLineOut(
                sku=line.sku,
                unit=line.unit,
                quantity=line.quantity,
                unit_credits=line.unit_credits,
                credits=line.credits,
            )
            for line in quoted_lines
        ],
    )


@router.post("/projects/{project_id}/operations", response_model=OperationJobsOut, status_code=202)
async def execute_project_operation(
    project_id: str,
    request: ProjectOperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "editor")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    if settings.billing_v2_enabled and request.pricing_catalog_id:
        catalog = await active_catalog(db)
        if catalog is None or catalog.id != request.pricing_catalog_id:
            raise HTTPException(status_code=409, detail="V-Credits 价格已更新，请重新确认本次费用")
    if project.script.revision != request.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "项目版本已变化，请刷新后重新选择操作范围",
                "client_revision": request.expected_revision,
                "server_revision": project.script.revision,
            },
        )

    project_level_operations = {"compose", "export", "generate_script"}
    scene_ids = _resolve_scene_ids(project, request.scope) if request.operation == "generate_voiceover" else []
    shot_ids = _resolve_shot_ids(project, request.scope) if request.operation not in project_level_operations | {"generate_voiceover"} else []
    if request.operation not in project_level_operations | {"generate_voiceover"} and not shot_ids:
        raise HTTPException(status_code=422, detail="当前作用范围内没有镜头")
    if request.operation == "generate_voiceover" and not scene_ids:
        raise HTTPException(status_code=422, detail="当前作用范围内没有场景")
    if request.operation in project_level_operations and request.scope.type != "project":
        raise HTTPException(status_code=422, detail="该操作只能作用于整个项目")

    jobs: list[Job] = []
    video_batch: VideoGenerationBatch | None = None
    billing_account = None
    if request.operation in {"generate_image", "generate_video", "generate_effect"}:
        plan = await active_plan_for_user(db, user)
        operation_kind = "image" if request.operation == "generate_image" else "video"
        try:
            validate_plan_generation_entitlements(
                plan,
                operation=operation_kind,
                resolution=str(request.parameters.get("resolution") or ""),
                batch=len(shot_ids) > 1,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    if request.operation == "generate_script":
        prompt = str(request.parameters.get("prompt") or "").strip()
        tone = str(request.parameters.get("tone") or "专业清晰").strip()[:50]
        try:
            duration_seconds = int(request.parameters.get("duration_seconds") or 60)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="目标时长必须是整数秒") from exc
        if not 10 <= len(prompt) <= 2000:
            raise HTTPException(status_code=422, detail="脚本需求需为 10–2000 个字符")
        if not 15 <= duration_seconds <= 300:
            raise HTTPException(status_code=422, detail="目标时长需为 15–300 秒")
        jobs.append(
            Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="project",
                subject_id=project.id,
                name="AI 生成项目脚本",
                type="AI 脚本生成",
                status="QUEUED",
                stage="等待生成",
                stages=["理解目标", "生成结构", "写入场景与镜头"],
                detail=f"目标 {duration_seconds} 秒 · {tone}",
                payload={
                    "project_id": project.id,
                    "prompt": prompt,
                    "tone": tone,
                    "duration_seconds": duration_seconds,
                    "include_asset_context": bool(request.parameters.get("include_asset_context", True)),
                },
            )
        )
    elif request.operation == "match_assets":
        jobs.append(
            Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="shot" if len(shot_ids) == 1 else "project",
                subject_id=shot_ids[0] if len(shot_ids) == 1 else project.id,
                name="镜头素材匹配",
                type="镜头匹配",
                status="QUEUED",
                stage="等待匹配",
                stages=["语义检索", "候选排序", "保存结果"],
                payload={"script_id": project.script.id, "shot_ids": shot_ids},
                detail=f"将匹配 {len(shot_ids)} 个镜头",
            )
        )
    elif request.operation == "complete_shots":
        jobs.append(
            Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="shot" if len(shot_ids) == 1 else "project",
                subject_id=shot_ids[0] if len(shot_ids) == 1 else project.id,
                name="AI 完善分镜",
                type="AI 分镜完善",
                status="QUEUED",
                stage="等待生成",
                stages=["完善描述", "等待确认"],
                payload={"script_id": project.script.id, "shot_ids": shot_ids},
            )
        )
    elif request.operation in {"generate_image", "generate_video", "generate_effect"}:
        config = {
            "generate_image": ("AI 生图分镜", "ai_image", "prompt"),
            "generate_video": ("分镜图 AI 生视频", "ai_video", "prompt"),
            "generate_effect": ("示意图特效视频", "ai_video", "motion_description"),
        }[request.operation]
        shots_by_id = {
            shot.id: shot for scene in project.script.units for shot in scene.shots
        }
        video_generation = _validated_video_generation(
            project,
            user.id,
            request.scope,
            shot_ids,
            request.parameters,
        ) if request.operation == "generate_video" else None
        video_job_specs: dict[str, tuple[str, str]] = {}
        if request.operation == "generate_video":
            from app.services.video_queue import ensure_video_queue_capacity

            try:
                await ensure_video_queue_capacity(db, user.id, project.id, len(shot_ids))
            except ValueError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            for shot_id in shot_ids:
                shot = shots_by_id[shot_id]
                prompt = _generation_prompt(shot, request.parameters, config[2])
                canonical = json.dumps(
                    {
                        "owner_id": user.id,
                        "project_id": project.id,
                        "shot_id": shot_id,
                        "shot_revision": shot.revision,
                        "prompt": prompt,
                        "video_generation": video_generation,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                video_job_specs[shot_id] = (
                    prompt,
                    hashlib.sha256(canonical.encode()).hexdigest(),
                )
            duplicate = (
                await db.execute(
                    select(Job.id).where(
                        Job.idempotency_key.in_([
                            item[1] for item in video_job_specs.values()
                        ]),
                        Job.status.in_(["QUEUED", "RUNNING", "PAUSED"]),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="相同镜头版本和生成参数已有任务在排队或执行，请勿重复提交",
                )
            video_batch = VideoGenerationBatch(
                owner_id=user.id,
                project_id=project.id,
                scope_type=request.scope.type,
                status="QUEUED",
                total_count=len(shot_ids),
            )
            db.add(video_batch)
            await db.flush()
        quota_probe = Job(owner_id=user.id)
        if not settings.billing_v2_enabled:
            try:
                await admit_job_quota(
                    db,
                    quota_probe,
                    user.id,
                    config[1],
                    len(shot_ids),
                )
            except QuotaExceededError as exc:
                raise HTTPException(status_code=403, detail="当前会员生成额度不足") from exc
        billing_sku, billing_quantity = _media_billing_sku(
            request.operation, request.parameters, video_generation
        )
        billing_account = (
            await ensure_user_billing_account(db, user, for_update=True)
            if settings.billing_v2_enabled
            else None
        )
        for shot_id in shot_ids:
            shot = shots_by_id[shot_id]
            prompt = (
                video_job_specs[shot_id][0]
                if video_batch
                else _generation_prompt(shot, request.parameters, config[2])
            )
            source_snapshot = {
                "asset_id": shot.asset_id,
                "selected_media_version_id": shot.selected_media_version_id,
                "visual_mode": shot.visual_mode,
                "source_start_ms": shot.source_start_ms,
                "source_end_ms": shot.source_end_ms,
                "transform": shot.transform or {},
                "adjust": shot.adjust or {},
                "motion": shot.motion or {},
            }
            idempotency_key = None
            if video_batch:
                idempotency_key = video_job_specs[shot_id][1]
            job = Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="shot",
                subject_id=shot_id,
                name=config[0],
                type=config[0],
                status="QUEUED",
                stage="等待调度" if video_batch else "等待生成",
                stages=["提交生成", "等待结果", "保存素材"],
                payload={
                    "shot_id": shot_id,
                    config[2]: prompt,
                    "base_shot_revision": shot.revision,
                    "source_snapshot": source_snapshot,
                    **({"billing_sku": billing_sku, "billing_quantity": billing_quantity} if settings.billing_v2_enabled else {}),
                    **({"video_generation": video_generation} if video_generation else {}),
                },
                batch_id=video_batch.id if video_batch else None,
                execution_state="QUEUED" if video_batch else None,
                idempotency_key=idempotency_key,
                queued_at=datetime.now(timezone.utc),
                quota_type=None if settings.billing_v2_enabled else config[1],
                quota_amount=0 if settings.billing_v2_enabled else 1,
            )
            jobs.append(job)
            db.add(job)
            if settings.billing_v2_enabled and billing_account is not None:
                try:
                    quote = await create_usage_quote(
                        db,
                        billing_account,
                        [{
                            "sku": billing_sku,
                            "quantity": billing_quantity,
                            "metadata": {"operation": request.operation, "shot_id": shot_id},
                        }],
                        request_snapshot={
                            "operation": request.operation,
                            "shot_id": shot_id,
                            "project_id": project.id,
                            "parameters": request.parameters,
                        },
                    )
                    await db.flush()
                    hold = await reserve_credits(
                        db,
                        billing_account,
                        quote.total_credits,
                        idempotency_key=f"job:{job.id}:quote:{quote.id}",
                        job_id=job.id,
                        quote_id=quote.id,
                        reason=f"{config[0]}积分预占",
                    )
                    job.billing_quote_id = quote.id
                    job.billing_hold_id = hold.id
                    job.quoted_credits = quote.total_credits
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if video_batch:
                raise HTTPException(
                    status_code=409,
                    detail="相同镜头版本和生成参数已有任务在排队或执行，请勿重复提交",
                ) from exc
            raise
    elif request.operation == "compose":
        jobs.append(
            Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="composition",
                subject_id=project.id,
                name="生成主成片",
                type="AI 初剪生成",
                status="QUEUED",
                stage="等待编排",
                stages=["检查镜头", "编排主成片", "保存结果"],
                payload={"project_id": project.id},
            )
        )
    elif request.operation == "generate_voiceover":
        if not settings.has_tts:
            raise HTTPException(status_code=503, detail="AI 配音未配置，请显式启用 AI_TTS_PROVIDER 并设置 DASHSCOPE_API_KEY")
        # 台词段是字幕与声音的唯一时间源。旧任务 payload 仍可携带 source，
        # 但新生成统一以实际字幕为准，避免另起一套场景旁白分段。
        source = "effective_subtitles"
        generate_mode = str(request.parameters.get("generate_mode") or "missing_and_stale")
        if generate_mode not in {"missing_only", "missing_and_stale", "force_regenerate"}:
            raise HTTPException(status_code=422, detail="配音生成模式无效")
        model = str(request.parameters.get("model") or settings.ai_tts_model).strip()
        voice = str(request.parameters.get("voice") or settings.ai_tts_voice).strip()
        if not model or not voice:
            raise HTTPException(status_code=422, detail="配音模型和音色不能为空")
        from app.services.tts.normalization import validate_tts_selection
        try:
            validate_tts_selection(model, voice)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        instruction = str(request.parameters.get("instruction") or "").strip()[:1600]
        jobs.append(
            Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="project" if request.scope.type == "project" else "scene",
                subject_id=project.id if request.scope.type == "project" else scene_ids[0],
                name="AI 生成字幕配音",
                type="AI 配音生成",
                status="QUEUED",
                stage="等待配音",
                stages=["解析字幕", "生成配音", "拼接旁白母带", "保存并应用"],
                detail=f"将处理 {len(scene_ids)} 个场景",
                payload={
                    "project_id": project.id,
                    "scene_ids": scene_ids,
                    "source": source,
                    "model": model,
                    "voice": voice,
                    "language": str(request.parameters.get("language") or settings.ai_tts_language),
                    "instruction": instruction,
                    "emotion": str(request.parameters.get("emotion") or "").strip()[:40],
                    "voice_line_ids": [str(item) for item in (request.parameters.get("voice_line_ids") or [])][:20],
                    "generate_mode": generate_mode,
                    "apply_after_success": bool(request.parameters.get("apply_after_success", True)),
                },
            )
        )
    else:
        export_format = str(request.parameters.get("format") or "mp4")
        resolution = str(request.parameters.get("resolution") or "1080p")
        aspect_ratio = str(request.parameters.get("aspect_ratio") or project.composition.aspect_ratio or "16:9")
        if export_format not in {"mp4", "mov"}:
            raise HTTPException(status_code=422, detail="导出格式仅支持 mp4 或 mov")
        if resolution not in {"480p", "720p", "1080p", "4k"}:
            raise HTTPException(status_code=422, detail="导出清晰度不受支持")
        if aspect_ratio not in {"16:9", "9:16", "1:1", "4:3"}:
            raise HTTPException(status_code=422, detail="导出画幅不受支持")
        job = Job(
            owner_id=user.id,
            project_id=project.id,
            subject_type="composition",
            subject_id=project.id,
            name="导出主成片",
            type="导出",
            status="QUEUED",
            stage="等待导出",
            stages=["准备素材", "渲染", "上传结果"],
            payload={
                "project_id": project.id,
                "format": export_format,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            },
        )
        if not settings.billing_v2_enabled:
            try:
                await admit_job_quota(db, job, user.id, "export", 1)
            except QuotaExceededError as exc:
                raise HTTPException(status_code=403, detail="当前会员导出额度不足") from exc
        jobs.append(job)

    # 文本、分镜和配音也走同一套报价 + 预占链路。媒体任务已经在上面
    # 按镜头逐个完成预占，这里跳过已有 billing_sku 的任务。
    if settings.billing_v2_enabled:
        billing_parameters = dict(request.parameters)
        if request.operation == "generate_voiceover" and jobs:
            billing_parameters["model"] = (jobs[0].payload or {}).get("model", "")
        non_media_spec = _operation_billing_sku(
            request.operation,
            project,
            scene_ids,
            billing_parameters,
        )
        if request.operation == "generate_voiceover" and request.parameters.get("voice_line_ids"):
            raw_line_ids = request.parameters["voice_line_ids"]
            if not isinstance(raw_line_ids, list):
                raise HTTPException(status_code=422, detail="配音段参数格式无效")
            requested_line_ids = list(dict.fromkeys(str(item) for item in raw_line_ids))
            durations = (
                await db.execute(
                    select(VoiceLine.target_duration_ms).where(
                        VoiceLine.project_id == project.id,
                        VoiceLine.id.in_(requested_line_ids),
                    )
                )
            ).scalars().all()
            if len(durations) != len(requested_line_ids):
                raise HTTPException(status_code=422, detail="部分配音段不存在或不属于当前项目")
            model = str(billing_parameters.get("model") or "").lower()
            sku = "tts.pro" if model.startswith("qwen-audio-") or "pro" in model else "tts.standard"
            non_media_spec = sku, max(1, math.ceil(sum(max(1, int(value)) for value in durations) / 60000))
        if non_media_spec and jobs:
            billing_account = billing_account or await ensure_user_billing_account(
                db, user, for_update=True
            )
            billing_sku, billing_quantity = non_media_spec
            for job in jobs:
                if (job.payload or {}).get("billing_sku"):
                    continue
                job.payload = {
                    **(job.payload or {}),
                    "billing_sku": billing_sku,
                    "billing_quantity": billing_quantity,
                }
                try:
                    quote = await create_usage_quote(
                        db,
                        billing_account,
                        [{
                            "sku": billing_sku,
                            "quantity": billing_quantity,
                            "metadata": {"operation": request.operation, "job_id": job.id},
                        }],
                        request_snapshot={
                            "operation": request.operation,
                            "project_id": project.id,
                            "parameters": request.parameters,
                        },
                    )
                    hold = await reserve_credits(
                        db,
                        billing_account,
                        quote.total_credits,
                        idempotency_key=f"job:{job.id}:quote:{quote.id}",
                        job_id=job.id,
                        quote_id=quote.id,
                        reason=f"{job.name}积分预占",
                    )
                    job.billing_quote_id = quote.id
                    job.billing_hold_id = hold.id
                    job.quoted_credits = quote.total_credits
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail=str(exc)) from exc

    project.status = "processing" if request.operation != "export" else "exporting"
    project.script.revision += 1
    project.composition.revision = project.script.revision
    for job in jobs:
        job.payload = {**(job.payload or {}), "base_revision": project.script.revision}
        db.add(job)
    await db.flush()
    await record_revision(
        db,
        project,
        user.id,
        "before_ai_operation",
        {
            "operation": request.operation,
            "scope": request.scope.model_dump(mode="json"),
            "job_ids": [job.id for job in jobs],
        },
    )
    await db.commit()

    for job in jobs:
        if job.type == "分镜图 AI 生视频":
            continue
        try:
            task = await _dispatch_job(db, project, job)
            job.celery_task_id = task.id
        except Exception as exc:
            await fail_job(
                db,
                job.id,
                stage="派发失败",
                detail=f"任务派发失败：{str(exc)[:200]}",
                error_code="DISPATCH_FAILED",
                error_category="INTERNAL_ERROR",
            )
            job.status = "FAILED"
            job.stage = "派发失败"
            job.detail = f"任务派发失败：{str(exc)[:200]}"
    await db.commit()
    if any(job.type == "分镜图 AI 生视频" for job in jobs):
        from app.services.video_queue import wake_video_scheduler

        wake_video_scheduler()
    return OperationJobsOut(
        jobs=[JobOut.model_validate(job) for job in jobs],
        video_batch=VideoGenerationBatchOut.model_validate(video_batch) if video_batch else None,
    )
