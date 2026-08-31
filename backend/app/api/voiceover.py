"""AI 配音工作台的只读状态和版本选择接口。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, ProjectAssetLink
from app.models.job import Job
from app.models.user import User
from app.models.voice import VoiceLine, VoiceProfile, VoiceTake
from app.services.project_access import require_project_access
from app.services.tts.normalization import dashscope_billable_characters, text_hash
from app.services.workspace import load_project_workspace, record_revision
from app.utils.storage import get_file_url


router = APIRouter()
settings = get_settings()


MODEL_OPTIONS = [
    {"id": "qwen-audio-3.0-tts-flash", "name": "剧情表现", "description": "支持情绪和拟声标签，适合剧情台词"},
    {"id": "qwen3-tts-instruct-flash", "name": "可控表达", "description": "使用自然语言控制语速、情绪和风格"},
    {"id": "qwen3-tts-flash", "name": "标准旁白", "description": "适合普通解说和快速草稿"},
]

VOICE_OPTIONS = {
    "qwen-audio-3.0-tts-flash": [
        {"id": "longanfengyue", "name": "龙安风悦", "description": "自然亲切女声"},
        {"id": "longanyuanfei", "name": "龙安元妃", "description": "高傲角色女声"},
        {"id": "longanlingxi", "name": "龙安灵希", "description": "可爱甜美女声"},
        {"id": "longanxiaoxin", "name": "龙安小昕", "description": "亲切活泼女声"},
        {"id": "longanhuan_v3.6", "name": "龙安欢", "description": "自然中文女声"},
        {"id": "longhuohuo_v3.6", "name": "龙火火", "description": "顽皮少年"},
        {"id": "longchuanshu_v3.6", "name": "龙川叔", "description": "川普大叔"},
    ],
    "qwen3-tts-instruct-flash": [
        {"id": "Cherry", "name": "Cherry", "description": "阳光积极、亲切自然女声"},
        {"id": "Serena", "name": "Serena", "description": "温柔女声"},
        {"id": "Ethan", "name": "Ethan", "description": "阳光温暖男声"},
        {"id": "Neil", "name": "Neil", "description": "专业新闻男声"},
        {"id": "Maia", "name": "Maia", "description": "知性温柔女声"},
    ],
    "qwen3-tts-flash": [
        {"id": "Cherry", "name": "Cherry", "description": "阳光积极、亲切自然女声"},
        {"id": "Serena", "name": "Serena", "description": "温柔女声"},
        {"id": "Ethan", "name": "Ethan", "description": "阳光温暖男声"},
        {"id": "Ryan", "name": "Ryan", "description": "富有张力的男声"},
        {"id": "Katerina", "name": "Katerina", "description": "成熟御姐女声"},
    ],
}


class EstimateRequest(BaseModel):
    source: str = Field("effective_subtitles", pattern="^(effective_subtitles|narration)$")
    scene_ids: list[str] = Field(default_factory=list)
    model: str = Field("qwen-audio-3.0-tts-flash", max_length=160)


class RegenerateLineRequest(BaseModel):
    expected_revision: int = Field(..., ge=0)
    model: str = Field(..., min_length=1, max_length=160)
    voice: str = Field(..., min_length=1, max_length=160)
    language: str = Field("Chinese", max_length=30)
    instruction: str = Field("", max_length=1600)
    emotion: str = Field("", max_length=40)


class ApplyMasterRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=64)
    expected_revision: int = Field(..., ge=0)


def _serialize_take(take: VoiceTake, asset: Asset | None) -> dict:
    return {
        "id": take.id,
        "assetId": take.asset_id,
        "jobId": take.job_id,
        "provider": take.provider,
        "model": take.model,
        "voiceId": take.voice_id,
        "requestId": take.request_id,
        "inputCharacters": take.input_characters,
        "billedCharacters": take.billed_characters,
        "durationMs": take.duration_ms,
        "timeStretchRatio": take.time_stretch_ratio,
        "qualityMetrics": take.quality_metrics or {},
        "isSelected": take.is_selected,
        "audioUrl": get_file_url(asset.file_path, expires_hours=2) if asset and asset.file_path else None,
        "createdAt": take.created_at.isoformat(),
    }


@router.get("/projects/{project_id}")
async def get_voiceover_workspace(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "viewer")
    project = await load_project_workspace(db, project_id, user.id)
    lines = (
        await db.execute(
            select(VoiceLine)
            .where(VoiceLine.project_id == project_id)
            .options(selectinload(VoiceLine.takes))
            .order_by(VoiceLine.start_ms, VoiceLine.line_index)
        )
    ).scalars().unique().all()
    asset_ids = {take.asset_id for line in lines for take in line.takes}
    assets = (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all() if asset_ids else []
    assets_by_id = {asset.id: asset for asset in assets}

    # GET 不修改数据库；以当前脚本重新规划，仅在响应中计算是否过期。
    from app.services.tts.planning import build_voice_plans
    selected_scene_ids = {scene.id for scene in project.script.units}
    expected_plans = build_voice_plans(project, selected_scene_ids, "effective_subtitles")
    expected_by_key = {plan["source_key"]: plan for plan in expected_plans}
    expected_by_position = {(plan["scene_id"], plan["line_index"]): plan for plan in expected_plans}

    profile_ids = {line.voice_profile_id for line in lines if line.voice_profile_id}
    profiles = (await db.execute(select(VoiceProfile).where(VoiceProfile.id.in_(profile_ids)))).scalars().all() if profile_ids else []
    profiles_by_id = {profile.id: profile for profile in profiles}
    items = []
    for line in lines:
        expected = expected_by_key.get(line.source_key)
        if expected is None and line.source_key.startswith("legacy:"):
            expected = expected_by_position.get((line.scene_id, line.line_index))
        stale_reasons: list[str] = []
        if expected is None:
            stale_reasons.append("cue_removed")
        else:
            if text_hash(expected["text"]) != line.text_hash:
                stale_reasons.append("text_changed")
            if expected["start_ms"] != line.start_ms:
                stale_reasons.append("start_changed")
            if expected["end_ms"] != line.end_ms:
                stale_reasons.append("end_changed")
            if expected.get("source_key") and expected["source_key"] != line.source_key:
                stale_reasons.append("source_key_changed")
        stale = bool(stale_reasons)
        profile = profiles_by_id.get(line.voice_profile_id or "")
        selected_take = next((take for take in line.takes if take.id == line.selected_take_id), None)
        overflow_ms = max(0, (selected_take.duration_ms if selected_take else 0) - line.speech_budget_ms)
        items.append({
            "id": line.id,
            "sourceKey": line.source_key,
            "sceneId": line.scene_id,
            "startShotId": line.start_shot_id,
            "endShotId": line.end_shot_id,
            "lineIndex": line.line_index,
            "text": line.text,
            "textSource": line.text_source,
            "sourceRevision": line.source_revision,
            "startMs": line.start_ms,
            "endMs": line.end_ms,
            "windowDurationMs": max(1, line.end_ms - line.start_ms),
            "targetDurationMs": line.target_duration_ms,
            "speechBudgetMs": line.speech_budget_ms,
            "pauseAfterMs": line.pause_after_ms,
            "captionEnabled": line.caption_enabled,
            "voiceEnabled": line.voice_enabled,
            "instruction": line.instruction,
            "emotion": line.emotion,
            "status": "stale" if stale else line.status,
            "timingStatus": "pending" if stale else line.timing_status,
            "overflowMs": overflow_ms,
            "staleReasons": stale_reasons,
            "expectedStartMs": expected["start_ms"] if expected else None,
            "expectedEndMs": expected["end_ms"] if expected else None,
            "expectedText": expected["text"] if expected else None,
            "selectedTakeId": line.selected_take_id,
            "voice": ({"model": profile.model, "voiceId": profile.voice_id, "name": profile.name} if profile else None),
            "takes": [_serialize_take(take, assets_by_id.get(take.asset_id)) for take in line.takes],
        })
    return {
        "enabled": settings.has_tts,
        "provider": settings.ai_tts_provider,
        "defaultModel": settings.ai_tts_model,
        "defaultVoice": settings.ai_tts_voice,
        "models": [{**model, "voices": VOICE_OPTIONS.get(model["id"], [])} for model in MODEL_OPTIONS],
        "lines": items,
    }


@router.post("/projects/{project_id}/estimate")
async def estimate_voiceover(
    project_id: str,
    request: EstimateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "viewer")
    from app.services.tts.normalization import validate_tts_selection
    try:
        # 估算只依赖模型价格；使用该模型首个 UI 音色完成同一份白名单校验。
        validate_tts_selection(request.model, VOICE_OPTIONS.get(request.model, [{}])[0].get("id", ""))
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=422, detail="不支持的配音模型") from exc
    project = await load_project_workspace(db, project_id, user.id)
    selected = set(request.scene_ids or [scene.id for scene in project.script.units])
    owned = {scene.id for scene in project.script.units}
    if not selected <= owned:
        raise HTTPException(status_code=422, detail="估算范围包含不属于当前项目的场景")
    from app.services.tts.planning import build_voice_plans
    plans = build_voice_plans(project, selected, request.source)
    characters = sum(dashscope_billable_characters(plan["text"]) for plan in plans)
    price_per_10k = 0.8 if request.model.startswith("qwen3-tts-") else 1.0
    return {"lineCount": len(plans), "billableCharacters": characters, "estimatedCostYuan": round(characters * price_per_10k / 10000, 4)}


@router.post("/projects/{project_id}/apply-master")
async def apply_voiceover_master(
    project_id: str,
    request: ApplyMasterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a generated master only when it exactly matches current cues.

    Generic workspace autosave intentionally rejects stale AI masters. This
    endpoint makes the same validation explicit so the UI never appears to
    accept a master that is immediately removed again.
    """
    await require_project_access(project_id, user, db, "editor")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    if project.script.revision != request.expected_revision:
        raise HTTPException(status_code=409, detail="项目版本已变化，请保存并刷新后重新选择旁白母带")
    asset = await db.get(Asset, request.asset_id)
    metadata = asset.asset_metadata or {} if asset else {}
    link = (
        await db.execute(
            select(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.asset_id == request.asset_id,
            )
        )
    ).scalar_one_or_none()
    if (
        not asset
        or asset.owner_id != user.id
        or not link
        or asset.source_type != "ai_tts"
        or metadata.get("purpose") != "voiceover_master"
        or metadata.get("projectId") != project_id
    ):
        raise HTTPException(status_code=422, detail="所选素材不是当前项目生成的 AI 旁白母带")

    from app.services.tts.planning import build_voice_plans
    expected_plans = build_voice_plans(project, {scene.id for scene in project.script.units}, "effective_subtitles")
    expected_by_key = {plan["source_key"]: plan for plan in expected_plans}
    expected_by_position = {(plan["scene_id"], plan["line_index"]): plan for plan in expected_plans}
    lines = (
        await db.execute(
            select(VoiceLine)
            .where(
                VoiceLine.project_id == project_id,
                VoiceLine.voice_enabled.is_(True),
            )
            .order_by(VoiceLine.start_ms, VoiceLine.line_index)
        )
    ).scalars().all()
    if len(lines) != len(expected_plans):
        raise HTTPException(status_code=409, detail="项目旁白台词尚未与当前字幕同步，请先保存项目并更新 AI 旁白")
    selected_take_ids: list[str] = []
    for line in lines:
        expected = expected_by_key.get(line.source_key)
        if expected is None and line.source_key.startswith("legacy:"):
            expected = expected_by_position.get((line.scene_id, line.line_index))
        valid = (
            expected is not None
            and text_hash(expected["text"]) == line.text_hash
            and expected["start_ms"] == line.start_ms
            and expected["end_ms"] == line.end_ms
            and line.status == "ready"
            and bool(line.selected_take_id)
        )
        if not valid:
            raise HTTPException(status_code=409, detail="该母带对应的字幕或时间已经变化，请先更新 AI 旁白")
        selected_take_ids.append(line.selected_take_id)
    if not selected_take_ids or set(metadata.get("voiceTakeIds") or []) != set(selected_take_ids):
        raise HTTPException(status_code=409, detail="该母带不是当前台词所选语音版本生成的，请重新生成旁白母带")

    project.composition.global_audio = {
        **(project.composition.global_audio or {}),
        "voiceAssetId": asset.id,
        "voiceMuted": False,
    }
    project.script.revision += 1
    project.composition.revision = project.script.revision
    await record_revision(
        db,
        project,
        user.id,
        "before_ai_operation",
        {"operation": "apply_voiceover_master", "master_asset_id": asset.id},
    )
    await db.commit()
    return {"assetId": asset.id, "revision": project.script.revision, "applied": True}


@router.post("/projects/{project_id}/lines/{line_id}/regenerate", status_code=202)
async def regenerate_voice_line(
    project_id: str,
    line_id: str,
    request: RegenerateLineRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "editor")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
    if project.script.revision != request.expected_revision:
        raise HTTPException(status_code=409, detail="项目版本已变化，请刷新后重新生成")
    line = await db.get(VoiceLine, line_id)
    if not line or line.project_id != project_id:
        raise HTTPException(status_code=404, detail="配音段不存在")
    source = "effective_subtitles"
    job = Job(
        owner_id=user.id, project_id=project_id, subject_type="voice_line", subject_id=line.id,
        name="重新生成单句配音", type="AI 配音生成", status="QUEUED", stage="等待配音",
        stages=["解析字幕", "生成配音", "拼接旁白母带", "保存并应用"],
        detail=line.text[:80],
        payload={
            "project_id": project_id, "scene_ids": [line.scene_id], "voice_line_ids": [line.id],
            "source": source, "model": request.model, "voice": request.voice,
            "language": request.language, "instruction": request.instruction, "emotion": request.emotion,
            "generate_mode": "force_regenerate", "apply_after_success": True,
        },
    )
    project.status = "processing"
    project.script.revision += 1
    project.composition.revision = project.script.revision
    job.payload = {**job.payload, "base_revision": project.script.revision}
    db.add(job)
    await db.flush()
    await record_revision(db, project, user.id, "before_ai_operation", {"operation": "regenerate_voice_line", "voice_line_id": line.id, "job_ids": [job.id]})
    await db.commit()
    from app.services.task_dispatch import dispatch_project_task
    from app.tasks.voice_tasks import generate_project_voiceover
    try:
        task = await dispatch_project_task(db, project_id, generate_project_voiceover, job.id, project_id)
        job.celery_task_id = task.id
    except Exception as exc:
        job.status = "FAILED"
        job.stage = "派发失败"
        job.detail = f"任务派发失败：{str(exc)[:200]}"
    await db.commit()
    from app.schemas.job import JobOut
    return JobOut.model_validate(job)
