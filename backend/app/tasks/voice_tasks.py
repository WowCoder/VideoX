"""AI 配音的段级生成、缓存复用与项目旁白母带任务。"""

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.generate_project_voiceover")
def generate_project_voiceover(self, job_id: str, project_id: str):
    try:
        run_async(_generate_project_voiceover(job_id, project_id))
    except Exception as exc:
        run_async(_mark_failed(job_id, exc))
        raise


async def _mark_failed(job_id: str, error: Exception) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.models.project import Project
    from app.services.quotas import fail_job

    async with async_session_factory() as session:
        completed = await fail_job(
            session,
            job_id,
            stage="配音失败",
            detail=f"AI 配音失败：{str(error)[:300]}",
            error_code="TTS_GENERATION_FAILED",
            error_category="PROVIDER_ERROR",
        )
        job = await session.get(Job, job_id)
        if completed and job:
            other_active_job = (
                await session.execute(
                    select(Job.id)
                    .where(
                        Job.project_id == job.project_id,
                        Job.id != job.id,
                        Job.status.in_(["QUEUED", "RUNNING"]),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not other_active_job:
                project = await session.get(Project, job.project_id)
                if project and project.status == "processing":
                    project.status = "ready"
        await session.commit()


async def _get_or_create_profile(session, *, owner_id: str, project_id: str, model: str, voice: str, language: str, instruction: str):
    from app.models.voice import VoiceProfile

    profile = (
        await session.execute(
            select(VoiceProfile).where(
                VoiceProfile.owner_id == owner_id,
                VoiceProfile.project_id == project_id,
                VoiceProfile.model == model,
                VoiceProfile.voice_id == voice,
                VoiceProfile.status == "active",
            )
        )
    ).scalars().first()
    if profile:
        return profile
    profile = VoiceProfile(
        owner_id=owner_id,
        project_id=project_id,
        name=f"{voice} · 项目声音",
        provider="dashscope",
        model=model,
        voice_id=voice,
        language=language,
        default_instruction=instruction,
    )
    session.add(profile)
    await session.flush()
    return profile


async def _sync_lines(session, project, plans: list[dict], profile, *, instruction: str, emotion: str, source_revision: int):
    from app.services.voice_cues import sync_voice_cues

    lines, _ = await sync_voice_cues(
        session,
        project,
        plans,
        source_revision=source_revision,
        profile_id=profile.id,
        instruction=instruction,
        emotion=emotion,
        scope_scene_ids={plan["scene_id"] for plan in plans},
    )
    return lines


async def _generate_project_voiceover(job_id: str, project_id: str) -> None:
    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.asset import Asset, ProjectAssetLink
    from app.models.job import Job
    from app.models.script import Script
    from app.models.voice import VoiceLine, VoiceTake
    from app.services.tts import DashScopeTTSProvider, TTSRequest
    from app.services.tts.mastering import build_master, normalize_take
    from app.services.tts.normalization import make_request_hash, validate_tts_selection
    from app.services.tts.planning import build_voice_plans
    from app.services.quotas import complete_job_success
    from app.services.storage_usage import recalculate_storage_usage
    from app.services.workspace import load_project_workspace, record_revision
    from app.utils.storage import download_file, upload_file

    settings = get_settings()
    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        if not job or job.project_id != project_id:
            raise RuntimeError("配音任务或项目不存在")
        project = await load_project_workspace(session, project_id, job.owner_id, for_update=True)
        payload = job.payload or {}
        base_revision = int(payload.get("base_revision", project.script.revision))
        if project.script.revision != base_revision:
            raise RuntimeError("项目已继续编辑，本次配音生成基线已过期")
        if not settings.has_tts:
            raise RuntimeError("AI 配音未配置；请显式启用 AI_TTS_PROVIDER 并设置 DASHSCOPE_API_KEY")
        scene_ids = set(payload.get("scene_ids") or [scene.id for scene in project.script.units])
        # 新旧任务都统一落到实际字幕 cue，避免重试旧 payload 时重新引入
        # “场景旁白”和“字幕”两套互相独立的时间线。
        source = "effective_subtitles"
        model = str(payload.get("model") or settings.ai_tts_model)
        voice = str(payload.get("voice") or settings.ai_tts_voice)
        validate_tts_selection(model, voice)
        language = str(payload.get("language") or settings.ai_tts_language)
        instruction = str(payload.get("instruction") or "").strip()
        emotion = str(payload.get("emotion") or "").strip()
        # 标准 Qwen3-TTS 不消费导演指令，Qwen3 系列也不消费 Qwen-Audio 情绪标签。
        # 将未实际发送的参数归一为空，避免相同供应商请求产生不同缓存键。
        if not (model.startswith("qwen-audio-") or model.startswith("qwen3-tts-instruct-")):
            instruction = ""
        if not model.startswith("qwen-audio-"):
            emotion = ""
        generate_mode = str(payload.get("generate_mode") or "missing_and_stale")
        apply_after_success = bool(payload.get("apply_after_success", True))
        job.status = "RUNNING"
        job.stage = "解析字幕"
        job.stage_index = 0
        job.progress = 5
        await session.commit()

        plans = build_voice_plans(project, scene_ids, source)
        if not plans:
            raise RuntimeError("当前范围内没有可用于配音的字幕或场景旁白")
        profile = await _get_or_create_profile(session, owner_id=job.owner_id, project_id=project_id, model=model, voice=voice, language=language, instruction=instruction)
        lines = await _sync_lines(session, project, plans, profile, instruction=instruction, emotion=emotion, source_revision=base_revision)
        job.stage = "生成配音"
        job.stage_index = 1
        job.progress = 10
        await session.commit()

        provider = DashScopeTTSProvider()
        generated = 0
        cached = 0
        billed = 0
        requested_line_ids = set(payload.get("voice_line_ids") or [])
        if requested_line_ids:
            lines = [line for line in lines if line.id in requested_line_ids]
            if not lines:
                raise RuntimeError("指定配音段已不存在，请刷新配音面板后重试")
        for index, line in enumerate(lines):
            await session.refresh(job)
            if job.status == "CANCELLED":
                return
            if len(line.text) > settings.ai_tts_max_text_characters:
                raise RuntimeError(
                    f"配音段文本超过 {settings.ai_tts_max_text_characters} 字符限制，请缩短字幕后重试"
                )
            request_hash = make_request_hash(provider="dashscope", model=model, voice=voice, text=line.text, language=language, instruction=instruction, emotion=emotion, target_duration_ms=line.target_duration_ms)
            # AsyncSession 禁止通过普通属性访问触发关系懒加载；显式 await 查询
            # 选中 Take，避免新建 VoiceLine 的未加载集合引发 MissingGreenlet。
            selected_take = await session.get(VoiceTake, line.selected_take_id) if line.selected_take_id else None
            if selected_take and selected_take.voice_line_id != line.id:
                selected_take = None
            missing = not line.selected_take_id or selected_take is None
            stale = (
                not missing
                and (selected_take.request_hash != request_hash or line.status in {"stale", "failed"})
            )
            should_generate = (
                generate_mode == "force_regenerate"
                or missing
                or (generate_mode == "missing_and_stale" and stale)
            )
            if not should_generate:
                continue
            # 只有同一逻辑台词可复用已经按其目标时长标准化过的 Take。
            # 跨台词复用会把别处的 atempo 结果带入当前时间窗口。
            cached_take = (
                await session.execute(
                    select(VoiceTake)
                    .join(Asset, Asset.id == VoiceTake.asset_id)
                    .where(
                        VoiceTake.voice_line_id == line.id,
                        VoiceTake.request_hash == request_hash,
                        VoiceTake.status == "ready",
                        Asset.owner_id == job.owner_id,
                        Asset.deleted_at.is_(None),
                    )
                    .order_by(VoiceTake.created_at.desc())
                )
            ).scalars().first()
            if cached_take and generate_mode != "force_regenerate":
                await session.execute(
                    update(VoiceTake)
                    .where(VoiceTake.voice_line_id == line.id, VoiceTake.is_selected.is_(True))
                    .values(is_selected=False)
                )
                cached_link = (
                    await session.execute(
                        select(ProjectAssetLink).where(
                            ProjectAssetLink.project_id == project_id,
                            ProjectAssetLink.asset_id == cached_take.asset_id,
                            ProjectAssetLink.role == "voiceover",
                        )
                    )
                ).scalar_one_or_none()
                if not cached_link:
                    session.add(ProjectAssetLink(project_id=project_id, asset_id=cached_take.asset_id, role="voiceover", linked_by=job.owner_id))
                take = VoiceTake(
                    voice_line_id=line.id, asset_id=cached_take.asset_id, job_id=job.id, provider=cached_take.provider,
                    model=cached_take.model, voice_id=cached_take.voice_id, request_id=cached_take.request_id,
                    request_hash=request_hash, input_characters=cached_take.input_characters, billed_characters=0,
                    duration_ms=cached_take.duration_ms, sample_rate=cached_take.sample_rate, channels=cached_take.channels,
                    time_stretch_ratio=cached_take.time_stretch_ratio, instruction=instruction,
                    parameters={**(cached_take.parameters or {}), "cache_hit": True}, quality_metrics=cached_take.quality_metrics or {}, is_selected=True,
                )
                session.add(take)
                await session.flush()
                line.selected_take_id = take.id
                if take.duration_ms > line.speech_budget_ms:
                    line.status = "timing_conflict"
                    line.timing_status = "conflict"
                else:
                    line.status = "ready"
                    line.timing_status = "fit"
                cached += 1
            else:
                if not line.selected_take_id:
                    line.status = "generating"
                await session.commit()
                result = await provider.synthesize(TTSRequest(text=line.text, model=model, voice=voice, language=language, instruction=instruction, emotion=emotion, request_hash=request_hash))
                content_type = result.content_type.lower()
                suffix = ".mp3" if "mpeg" in content_type else ".wav" if "wav" in content_type else ".opus" if "opus" in content_type else ".audio"
                raw_handle = tempfile.NamedTemporaryFile(prefix="openvma_tts_raw_", suffix=suffix, delete=False)
                normalized_handle = tempfile.NamedTemporaryFile(prefix="openvma_tts_norm_", suffix=".wav", delete=False)
                raw_path, normalized_path = raw_handle.name, normalized_handle.name
                raw_handle.write(result.audio_bytes)
                raw_handle.close()
                normalized_handle.close()
                try:
                    metrics = normalize_take(raw_path, normalized_path, target_duration_ms=line.target_duration_ms)
                    with open(normalized_path, "rb") as stream:
                        normalized_bytes = stream.read()
                    checksum = hashlib.sha256(normalized_bytes).hexdigest()
                    object_path = f"generated/{project_id}/voice/{line.id}/{uuid.uuid4().hex}.wav"
                    upload_file(object_path, normalized_bytes, "audio/wav")
                finally:
                    for temporary in (raw_path, normalized_path):
                        try:
                            os.unlink(temporary)
                        except OSError:
                            pass
                asset = Asset(
                    owner_id=job.owner_id, name=f"配音 · {line.text[:24]}", media_type="audio", source_type="ai_tts",
                    status="ready", processing_status="ready", mime_type="audio/wav", file_path=object_path,
                    file_size_mb=round(len(normalized_bytes) / 1024 / 1024, 4), checksum=checksum,
                    duration_ms=metrics["duration_ms"], codec="pcm_s16le", has_audio=True, audio_codec="pcm_s16le",
                    sample_rate=metrics["sample_rate"], channels=metrics["channels"], ai_provider="dashscope", ai_model=model,
                    ai_prompt=line.text, asset_metadata={"purpose": "voice_take", "voiceLineId": line.id, "requestId": result.provider_request_id, "requestHash": request_hash, "textHash": line.text_hash, "voiceId": voice, "inputCharacters": result.input_characters, "billedCharacters": result.billed_characters, "sourceRevision": base_revision, "timeStretchRatio": metrics["time_stretch_ratio"], "overflowMs": metrics["overflow_ms"]},
                )
                session.add(asset)
                await session.flush()
                session.add(ProjectAssetLink(project_id=project_id, asset_id=asset.id, role="voiceover", linked_by=job.owner_id))
                await session.execute(
                    update(VoiceTake)
                    .where(VoiceTake.voice_line_id == line.id, VoiceTake.is_selected.is_(True))
                    .values(is_selected=False)
                )
                take = VoiceTake(
                    voice_line_id=line.id, asset_id=asset.id, job_id=job.id, provider="dashscope", model=model, voice_id=voice,
                    request_id=result.provider_request_id, request_hash=request_hash, input_characters=result.input_characters,
                    billed_characters=result.billed_characters, duration_ms=metrics["duration_ms"], sample_rate=metrics["sample_rate"],
                    channels=metrics["channels"], time_stretch_ratio=metrics["time_stretch_ratio"], instruction=instruction,
                    parameters={"language": language, "emotion": emotion, "target_duration_ms": line.target_duration_ms}, quality_metrics={"overflowMs": metrics["overflow_ms"], "decodeValid": True}, is_selected=True,
                )
                session.add(take)
                await session.flush()
                line.selected_take_id = take.id
                if metrics["overflow_ms"] > 0:
                    line.status = "timing_conflict"
                    line.timing_status = "conflict"
                else:
                    line.status = "ready"
                    line.timing_status = "fit"
                generated += 1
                billed += result.billed_characters
            job.progress = min(78, 10 + round(68 * (index + 1) / len(lines)))
            job.detail = f"已处理 {index + 1}/{len(lines)} 条配音"
            await session.commit()

        conflicts = [line for line in lines if line.voice_enabled and line.status == "timing_conflict"]
        if conflicts:
            preview = "、".join(f"第 {line.line_index + 1} 段" for line in conflicts[:3])
            raise RuntimeError(
                f"{preview} 的语音明显超过字幕时间窗；已保留生成版本，但没有覆盖当前旁白母带。"
                "请精简字幕、延长镜头或更换更快的表达后重试"
            )

        project_conflicts = (
            await session.execute(
                select(VoiceLine).where(
                    VoiceLine.project_id == project_id,
                    VoiceLine.voice_enabled.is_(True),
                    VoiceLine.status == "timing_conflict",
                )
            )
        ).scalars().all()
        if project_conflicts:
            raise RuntimeError("项目仍有配音超过字幕时间窗，请先处理冲突台词再应用旁白母带")

        # 用户编辑可能发生在外部语音调用期间；保留已生成 Take，但禁止应用到新版本。
        current_revision = (await session.execute(select(Script.revision).where(Script.id == project.script.id))).scalar_one()
        if current_revision != base_revision:
            raise RuntimeError("配音生成期间项目已继续编辑；结果已保留为候选，但未应用到当前时间线")

        job.stage = "拼接旁白母带"
        job.stage_index = 2
        job.progress = 82
        await session.commit()
        all_lines = (
            await session.execute(
                select(VoiceLine).where(
                    VoiceLine.project_id == project_id,
                    VoiceLine.voice_enabled.is_(True),
                    VoiceLine.selected_take_id.is_not(None),
                    VoiceLine.status == "ready",
                ).order_by(VoiceLine.start_ms)
            )
        ).scalars().all()
        selected_take_ids = [line.selected_take_id for line in all_lines if line.selected_take_id]
        takes = (
            await session.execute(select(VoiceTake).where(VoiceTake.id.in_(selected_take_ids)).options(selectinload(VoiceTake.voice_line)))
        ).scalars().all()
        takes_by_id = {take.id: take for take in takes}
        asset_ids = [take.asset_id for take in takes]
        assets = (await session.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
        assets_by_id = {asset.id: asset for asset in assets}
        temp_dir = tempfile.mkdtemp(prefix="openvma_voice_master_")
        try:
            clips: list[tuple[str, int]] = []
            for clip_index, line in enumerate(all_lines):
                take = takes_by_id.get(line.selected_take_id or "")
                asset = assets_by_id.get(take.asset_id) if take else None
                if not asset or not asset.file_path:
                    continue
                local = os.path.join(temp_dir, f"{clip_index:04d}.wav")
                download_file(asset.file_path, local)
                clips.append((local, line.start_ms))
            if not clips:
                raise RuntimeError("没有可用于拼接母带的已选配音")
            total_duration_ms = sum(max(1, shot.duration_ms) for scene in project.script.units for shot in scene.shots)
            master_path = os.path.join(temp_dir, "voiceover-master.wav")
            master_metrics = build_master(clips=clips, duration_ms=total_duration_ms, output_path=master_path)
            with open(master_path, "rb") as stream:
                master_bytes = stream.read()
            master_object = f"generated/{project_id}/voice/master/{uuid.uuid4().hex}.wav"
            upload_file(master_object, master_bytes, "audio/wav")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        master_asset = Asset(
            owner_id=job.owner_id, name="AI 旁白母带", media_type="audio", source_type="ai_tts",
            status="ready", processing_status="ready", mime_type="audio/wav", file_path=master_object,
            file_size_mb=round(len(master_bytes) / 1024 / 1024, 4), checksum=hashlib.sha256(master_bytes).hexdigest(),
            duration_ms=master_metrics["duration_ms"], codec="pcm_s16le", has_audio=True, audio_codec="pcm_s16le",
            sample_rate=master_metrics["sample_rate"], channels=master_metrics["channels"], ai_provider="dashscope", ai_model=model,
            asset_metadata={"purpose": "voiceover_master", "projectId": project_id, "baseRevision": base_revision, "voiceTakeIds": selected_take_ids},
        )
        session.add(master_asset)
        await session.flush()
        session.add(ProjectAssetLink(project_id=project_id, asset_id=master_asset.id, role="voiceover", linked_by=job.owner_id))
        await recalculate_storage_usage(session, job.owner_id)
        if apply_after_success:
            project.composition.global_audio = {**(project.composition.global_audio or {}), "voiceAssetId": master_asset.id}
        project.script.revision += 1
        project.composition.revision = project.script.revision
        project.status = "ready"
        await record_revision(session, project, job.owner_id, "before_ai_operation", {"operation": "apply_voiceover", "job_id": job.id, "master_asset_id": master_asset.id, "generated": generated, "cached": cached})
        completed = await complete_job_success(
            session,
            job.id,
            values={
                "stage": "配音已完成",
                "stage_index": 3,
                "progress": 100,
                "detail": f"配音完成：新生成 {generated} 条，缓存复用 {cached} 条",
                "result": "打开项目工作台",
                "result_detail": f"已生成旁白母带；本次供应商计费字符约 {billed}",
                "result_path": master_object,
                "payload": {
                    **payload,
                    "master_asset_id": master_asset.id,
                    "generated_count": generated,
                    "cache_hit_count": cached,
                    "billed_characters": billed,
                },
            },
        )
        if not completed:
            await session.rollback()
            return
        await session.commit()
