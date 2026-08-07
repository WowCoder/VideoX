"""AI 生成路由：脚本生成/生图/生视频/特效。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, Usage
from app.models.project import Project
from app.models.asset import Asset, Clip
from app.models.script import Script, ScriptUnit, Shot, ShotGeneration
from app.models.job import Job
from app.services.ai_provider import generate_script_with_ai
from app.config import get_settings
from app.services.project_access import require_project_access
from app.services.timeline_validation import TimelineValidationError, validate_project_timeline

router = APIRouter()
settings = get_settings()


class GenerateScriptRequest(BaseModel):
    """AI 脚本生成请求。"""
    project_id: str
    brief: str = Field(..., min_length=1, max_length=300, description="需求描述")
    target_duration: int = Field(60, description="目标时长（秒）")
    tone: str = Field("专业克制", description="表达语气")
    reference_dialogue: bool = Field(False, description="是否参考素材对白")


class GenerateScriptResponse(BaseModel):
    """AI 脚本生成响应。"""
    title: str
    summary: str
    units: list[dict]


class GenerateImageRequest(BaseModel):
    """AI 生图请求。"""
    shot_id: str
    prompt: str = ""
    project_id: str = ""


class GenerateVideoRequest(BaseModel):
    """图生视频请求。"""
    shot_id: str
    prompt: str = ""
    project_id: str = ""


class GenerateEffectRequest(BaseModel):
    """示意特效请求。"""
    shot_id: str
    sketch_data: str = Field(..., min_length=32, max_length=4_000_000)
    motion_description: str = Field("", max_length=1000)
    project_id: str = ""


class GenerateJobResponse(BaseModel):
    """AI 生成任务响应。"""
    job_id: str
    message: str


class GenerationCapability(BaseModel):
    available: bool
    model: str = ""
    reason: str = ""


class GenerationCapabilitiesResponse(BaseModel):
    image: GenerationCapability
    image_to_video: GenerationCapability
    effect_video: GenerationCapability


@router.get("/capabilities", response_model=GenerationCapabilitiesResponse)
async def generation_capabilities(_: User = Depends(get_current_user)):
    """返回真实生成能力，供前端在操作前禁用不可用入口。"""
    has_key = settings.has_dashscope
    return GenerationCapabilitiesResponse(
        image=GenerationCapability(
            available=settings.has_image_generation,
            model=settings.ai_image_model if settings.has_image_generation else "",
            reason="" if settings.has_image_generation else "AI 生图服务未配置",
        ),
        image_to_video=GenerationCapability(
            available=settings.has_image_to_video,
            model=settings.ai_image_to_video_model if settings.has_image_to_video else "",
            reason=(
                ""
                if settings.has_image_to_video
                else "请配置 DASHSCOPE_API_KEY 与 AI_IMAGE_TO_VIDEO_MODEL"
                if not has_key or not settings.ai_image_to_video_model
                else "图生视频服务未启用"
            ),
        ),
        effect_video=GenerationCapability(
            available=settings.has_effect_video,
            model=settings.ai_effect_video_model if settings.has_effect_video else "",
            reason=(
                ""
                if settings.has_effect_video
                else "请配置 DASHSCOPE_API_KEY 与 AI_EFFECT_VIDEO_MODEL"
                if not has_key or not settings.ai_effect_video_model
                else "示意特效视频服务未启用"
            ),
        ),
    )


async def _check_quota(project: Project, db: AsyncSession, quota_type: str) -> bool:
    """检查配额是否足够。"""
    result = await db.execute(select(Usage).where(Usage.user_id == project.owner_id))
    usage = result.scalar_one_or_none()
    if not usage:
        return True  # 无用量记录，允许

    from app.models.user import Membership
    owner = (
        await db.execute(select(User).where(User.id == project.owner_id))
    ).scalar_one()
    mem_result = await db.execute(select(Membership).where(Membership.id == owner.membership_id))
    membership = mem_result.scalar_one_or_none()
    if not membership:
        return True

    if quota_type == "image":
        pending = (
            await db.execute(
                select(func.count()).select_from(Job).join(Project).where(
                    Project.owner_id == project.owner_id,
                    Job.type == "AI 生图分镜",
                    Job.status.in_(["QUEUED", "RUNNING"]),
                )
            )
        ).scalar() or 0
        return usage.ai_image_used + pending < membership.ai_image_quota
    elif quota_type == "video":
        pending = (
            await db.execute(
                select(func.count()).select_from(Job).join(Project).where(
                    Project.owner_id == project.owner_id,
                    Job.type.in_(["分镜图 AI 生视频", "示意图特效视频"]),
                    Job.status.in_(["QUEUED", "RUNNING"]),
                )
            )
        ).scalar() or 0
        return usage.ai_video_used + pending < membership.ai_video_quota
    return True


async def _editable_shot(
    shot_id: str, project_id: str, user: User, db: AsyncSession
) -> tuple[Shot, Project]:
    project = (await require_project_access(project_id, user, db, "editor")).project
    result = await db.execute(
        select(Shot)
        .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
        .join(Script, ScriptUnit.script_id == Script.id)
        .join(Project, Script.project_id == Project.id)
        .where(
            Shot.id == shot_id,
            Project.id == project_id,
        )
    )
    shot = result.scalar_one_or_none()
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在或不属于当前项目")
    return shot, project


async def _build_project_script_context(project_id: str, db: AsyncSession) -> str:
    """读取项目真实素材摘要，并限制上下文体积以控制模型费用。"""
    rows = (
        await db.execute(
            select(Asset.name, Clip)
            .join(Clip, Clip.asset_id == Asset.id)
            .where(
                Asset.project_id == project_id,
                Asset.status == "处理完成",
                or_(
                    Clip.transcript_segment != "",
                    Clip.ocr_segment != "",
                    Clip.scene_type.is_not(None),
                ),
            )
            .order_by(Clip.quality_score.desc(), Clip.created_at)
            .limit(24)
        )
    ).all()

    entries: list[str] = []
    total_length = 0
    max_length = 6000
    for asset_name, clip in rows:
        parts = [
            f"素材：{asset_name}",
            f"时间：{clip.start_time:.1f}-{clip.end_time:.1f}秒",
        ]
        if clip.transcript_segment.strip():
            parts.append(f"对白：{clip.transcript_segment.strip()[:500]}")
        if clip.ocr_segment.strip():
            parts.append(f"画面文字：{clip.ocr_segment.strip()[:300]}")
        if clip.scene_type:
            parts.append(f"场景：{clip.scene_type}")
        if clip.persons:
            parts.append(f"人物：{'、'.join(str(item) for item in clip.persons[:8])}")
        if clip.objects:
            parts.append(f"物品：{'、'.join(str(item) for item in clip.objects[:8])}")
        entry = "；".join(parts)
        if total_length + len(entry) > max_length:
            break
        entries.append(entry)
        total_length += len(entry)

    if entries:
        return "\n".join(f"{index}. {entry}" for index, entry in enumerate(entries, 1))

    # 兼容只保存了 Asset 级完整转写的旧素材。
    asset_rows = (
        await db.execute(
            select(Asset.name, Asset.transcript, Asset.ocr_text)
            .where(
                Asset.project_id == project_id,
                Asset.status == "处理完成",
                or_(Asset.transcript.is_not(None), Asset.ocr_text.is_not(None)),
            )
            .order_by(Asset.uploaded_at.desc())
            .limit(6)
        )
    ).all()
    for asset_name, transcript, ocr_text in asset_rows:
        parts = [f"素材：{asset_name}"]
        if transcript and transcript.strip():
            parts.append(f"对白：{transcript.strip()[:1200]}")
        if ocr_text and ocr_text.strip():
            parts.append(f"画面文字：{ocr_text.strip()[:500]}")
        entry = "；".join(parts)
        if total_length + len(entry) > max_length:
            break
        entries.append(entry)
        total_length += len(entry)
    return "\n".join(f"{index}. {entry}" for index, entry in enumerate(entries, 1))


@router.post("/script", response_model=GenerateScriptResponse)
async def generate_script(
    req: GenerateScriptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 生成脚本。

    调用阿里千问 LLM 生成结构化脚本，返回预览数据（不保存）。
    前端确认后再调用 POST /api/scripts 创建。
    """
    await require_project_access(req.project_id, user, db, "editor")
    if not settings.has_text_generation:
        raise HTTPException(status_code=503, detail="文本生成服务未配置或不可用")
    try:
        dialogue_context = (
            await _build_project_script_context(req.project_id, db)
            if req.reference_dialogue
            else ""
        )
        result = await generate_script_with_ai(
            brief=req.brief,
            target_duration=req.target_duration,
            tone=req.tone,
            reference_dialogue=req.reference_dialogue,
            dialogue_context=dialogue_context,
        )
        return GenerateScriptResponse(
            title=result.get("title", "AI 生成脚本"),
            summary=result.get("summary", req.brief),
            units=result.get("units", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 生成失败：{str(e)}")


@router.post("/image", response_model=GenerateJobResponse)
async def generate_image_shot(
    req: GenerateImageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 生图分镜。

    创建异步任务，调用通义万相生成关键帧。
    """
    shot, project = await _editable_shot(req.shot_id, req.project_id, user, db)
    if not settings.has_image_generation:
        raise HTTPException(status_code=503, detail="AI 生图服务未配置或不可用")
    if not await _check_quota(project, db, "image"):
        raise HTTPException(status_code=403, detail="项目所有者的 AI 生图配额已用完")

    # 创建任务
    job = Job(
        project_id=req.project_id,
        name=f"AI 生图分镜：{shot.description[:20]}",
        type="AI 生图分镜",
        status="QUEUED",
        stage="等待生成",
        stages=["理解分镜", "生成构图", "筛选关键帧", "写入脚本"],
        stage_index=0,
        progress=0,
        eta="预计 1-2 分钟",
        detail="AI 生图任务已进入队列",
        result=None,
        result_detail="",
        payload={"shot_id": shot.id, "prompt": req.prompt},
        is_simulated=False,
    )
    db.add(job)
    await db.flush()

    await db.commit()

    # 派发 Celery 任务
    from app.tasks.generate_tasks import generate_image_shot as celery_generate_image
    try:
        task = celery_generate_image.delay(shot.id, job.id, req.prompt)
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"AI 生图任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后重试"
        await db.commit()

    return GenerateJobResponse(job_id=job.id, message="AI 生图任务已创建")


@router.post("/video", response_model=GenerateJobResponse)
async def generate_video_shot(
    req: GenerateVideoRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """图生视频。"""
    shot, project = await _editable_shot(req.shot_id, req.project_id, user, db)
    if not settings.has_image_to_video:
        raise HTTPException(
            status_code=503,
            detail="图生视频模型未配置；请在百炼确认真实模型名后设置 AI_IMAGE_TO_VIDEO_MODEL",
        )
    image_generation = (
        await db.execute(
            select(ShotGeneration.id)
            .where(
                ShotGeneration.shot_id == shot.id,
                ShotGeneration.kind == "image",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if not shot.generated_image_path and not image_generation:
        raise HTTPException(status_code=400, detail="当前分镜没有可用于图生视频的持久化关键帧")
    if not await _check_quota(project, db, "video"):
        raise HTTPException(status_code=403, detail="项目所有者的 AI 生视频配额已用完")

    job = Job(
        project_id=req.project_id,
        name=f"图生视频：{shot.description[:20]}",
        type="分镜图 AI 生视频",
        status="QUEUED",
        stage="等待生成",
        stages=["读取分镜图", "解析运镜", "生成视频", "加入粗剪候选"],
        stage_index=0,
        progress=0,
        eta="预计 2-5 分钟",
        detail="图生视频任务已进入队列",
        result=None,
        result_detail="",
        payload={"shot_id": shot.id, "prompt": req.prompt},
        is_simulated=False,
    )
    db.add(job)
    await db.flush()

    await db.commit()

    from app.tasks.generate_tasks import generate_video_shot as celery_generate_video
    try:
        task = celery_generate_video.delay(shot.id, job.id, req.prompt)
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"图生视频任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后重试"
        await db.commit()

    return GenerateJobResponse(job_id=job.id, message="图生视频任务已创建")


@router.post("/effect", response_model=GenerateJobResponse)
async def generate_effect_shot(
    req: GenerateEffectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """示意特效生成。"""
    shot, project = await _editable_shot(req.shot_id, req.project_id, user, db)
    if not settings.has_effect_video:
        raise HTTPException(
            status_code=503,
            detail="示意特效视频模型未配置；不能使用普通文生视频模型冒充该能力",
        )
    if not await _check_quota(project, db, "video"):
        raise HTTPException(status_code=403, detail="项目所有者的 AI 生成配额已用完")
    if not req.sketch_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="示意特效需要有效的 Canvas 图片")

    # 草图只保存到 Shot，避免把大段 Base64 再复制进 Job payload 和消息队列。
    shot.sketch_data = req.sketch_data

    job = Job(
        project_id=req.project_id,
        name=f"示意特效：{shot.description[:20]}",
        type="示意图特效视频",
        status="QUEUED",
        stage="等待生成",
        stages=["识别示意图", "理解运动轨迹", "生成特效", "加入粗剪"],
        stage_index=0,
        progress=0,
        eta="预计 1-3 分钟",
        detail="示意特效任务已进入队列",
        result=None,
        result_detail="",
        payload={
            "shot_id": shot.id,
            "has_sketch": True,
            "motion_description": req.motion_description,
        },
        is_simulated=False,
    )
    db.add(job)
    await db.flush()

    await db.commit()

    from app.tasks.generate_tasks import generate_effect_shot as celery_generate_effect
    try:
        task = celery_generate_effect.delay(shot.id, job.id, req.motion_description)
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"示意特效任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后重试"
        await db.commit()

    return GenerateJobResponse(job_id=job.id, message="示意特效任务已创建")


# ── 导出路由 ──
class ExportRequest(BaseModel):
    """导出请求。"""
    project_id: str
    cut_version_id: str | None = None
    format: Literal["mp4", "mov", "prores"] = "mp4"
    resolution: Literal["480p", "720p", "1080p", "4k"] = "1080p"


class ExportResponse(BaseModel):
    """导出响应。"""
    job_id: str
    message: str


@router.post("/export", response_model=ExportResponse)
async def export_project(
    req: ExportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出成片。"""
    project = (await require_project_access(req.project_id, user, db, "editor")).project
    timeline = project.timeline or []
    if req.cut_version_id:
        from app.models.cut_version import CutVersion

        cut_version = await db.get(CutVersion, req.cut_version_id)
        if not cut_version or cut_version.project_id != project.id:
            raise HTTPException(status_code=404, detail="剪辑版本不存在或不属于当前项目")
        timeline = cut_version.timeline or []

    placeholder_clips = [
        clip for clip in timeline
        if clip.get("track") == "video" and clip.get("origin") == "script_placeholder"
    ]
    if placeholder_clips:
        first_name = placeholder_clips[0].get("name") or "未命名分镜"
        raise HTTPException(
            status_code=400,
            detail=(
                f"时间线仍有 {len(placeholder_clips)} 个待补素材分镜，"
                f"请先补齐「{first_name}」后再导出"
            ),
        )

    video_clips = [
        clip for clip in timeline
        if clip.get("track") == "video"
        and (clip.get("asset_id") or clip.get("generated_media_path"))
    ]
    if not video_clips:
        raise HTTPException(status_code=400, detail="时间线中没有可导出的视频素材")

    try:
        await validate_project_timeline(project, timeline, db, user)
    except TimelineValidationError as exc:
        raise HTTPException(status_code=400, detail=f"导出前检查失败：{exc}") from exc

    # 检查导出配额
    result = await db.execute(select(Usage).where(Usage.user_id == project.owner_id))
    usage = result.scalar_one_or_none()
    if not usage:
        usage = Usage(user_id=project.owner_id)
        db.add(usage)
        await db.flush()

    from app.models.user import Membership
    owner = (
        await db.execute(select(User).where(User.id == project.owner_id))
    ).scalar_one()
    mem_result = await db.execute(select(Membership).where(Membership.id == owner.membership_id))
    membership = mem_result.scalar_one_or_none()

    pending_exports = (
        await db.execute(
            select(func.count())
            .select_from(Job)
            .join(Project)
            .where(
                Project.owner_id == project.owner_id,
                Job.type == "导出",
                Job.status.in_(["QUEUED", "RUNNING"]),
            )
        )
    ).scalar() or 0
    if membership and usage.export_used + pending_exports >= membership.export_quota:
        raise HTTPException(status_code=403, detail="导出配额已用完，请升级会员")

    # 创建导出任务
    job = Job(
        project_id=req.project_id,
        name=f"导出：{req.format} {req.resolution}",
        type="导出",
        status="QUEUED",
        stage="等待导出",
        stages=["准备时间线", "渲染视频轨", "混合音频轨", "烧录字幕", "编码输出"],
        stage_index=0,
        progress=0,
        eta="预计 1-5 分钟",
        detail=f"{req.format} {req.resolution} 导出任务已进入队列",
        result=None,
        result_detail="",
        payload={
            "project_id": req.project_id,
            "cut_version_id": req.cut_version_id,
            "format": req.format,
            "resolution": req.resolution,
        },
        is_simulated=False,
    )
    db.add(job)
    await db.commit()

    # 派发 Celery 任务
    from app.tasks.export_tasks import export_project as celery_export
    try:
        task = celery_export.delay(
            req.project_id, job.id, req.format, req.resolution, req.cut_version_id or ""
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"导出任务派发失败：{str(exc)[:200]}"
        job.result_detail = "请确认 Redis 和 Worker 正常运行后重试"
        await db.commit()

    return ExportResponse(job_id=job.id, message="导出任务已创建")


# ── 会员与用量路由 ──
from app.schemas.auth import MembershipOut, UsageOut
from fastapi import Body


@router.get("/memberships", response_model=list[MembershipOut])
async def list_memberships(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取会员方案列表。"""
    from app.models.user import Membership
    result = await db.execute(select(Membership).order_by(Membership.rank))
    return [MembershipOut.model_validate(m) for m in result.scalars().all()]


@router.get("/usage", response_model=UsageOut)
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用量。"""
    result = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = result.scalar_one_or_none()
    if not usage:
        usage = Usage(user_id=user.id)
        db.add(usage)
        await db.flush()
    return UsageOut.model_validate(usage)
