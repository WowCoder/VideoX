"""AI 初剪装配 Celery 任务。

对应详设 3.3 createProjectFromScript 的后端异步部分：
遍历脚本单元 → 匹配真实素材 / 标记缺失镜头 → 装配多轨初剪
"""

from datetime import datetime, timezone
import uuid

from app.tasks.celery_app import celery_app
from app.tasks.async_runner import run_async


MIN_TIMELINE_CLIP_DURATION = 0.5


def _positive_duration(value, fallback: float = 8.0) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        duration = fallback
    return max(MIN_TIMELINE_CLIP_DURATION, duration if duration > 0 else fallback)


def _timeline_clip(
    script,
    unit,
    shot,
    *,
    start: float,
    duration: float,
    name: str,
    variant: str,
    origin: str,
    asset_id=None,
    source_clip_id=None,
    source_start: float = 0.0,
    generated_media_path=None,
    generated_media_type=None,
    text=None,
) -> dict:
    return {
        "id": f"timeline-{uuid.uuid4().hex[:12]}",
        "track": "subtitle" if origin == "script_subtitle" else "video",
        "start": round(start, 3),
        "duration": round(duration, 3),
        "name": name,
        "variant": variant,
        "asset_id": asset_id,
        "source_clip_id": source_clip_id,
        "source_start": round(source_start, 3),
        "source_script_id": script.parent_script_id,
        "source_unit_id": unit.source_unit_id,
        "source_shot_id": shot.source_shot_id if shot else None,
        "snapshot_script_id": script.id,
        "snapshot_unit_id": unit.id,
        "snapshot_shot_id": shot.id if shot else None,
        "generated_media_path": generated_media_path,
        "generated_media_type": generated_media_type,
        "origin": origin,
        "sync_status": "synced",
        "text": text,
        "transform": {
            "scale": 100, "x": 0, "y": 0, "rotation": 0, "opacity": 100,
            "crop": {"l": 0, "t": 0, "r": 0, "b": 0},
        },
        "adjust": {"brightness": 100, "contrast": 100, "saturation": 100},
        "audio": {"volume": 100, "denoise": False},
        "transition": {"type": "none", "duration": 0.5},
    }


def _assemble_script_timeline(script, media_by_shot: dict[str, dict]) -> tuple[list[dict], dict[str, int]]:
    """把完整脚本编译成时间线；每个分镜都保留脚本目标时间位置。"""
    timeline: list[dict] = []
    cursor = 0.0
    stats = {"matched": 0, "generated": 0, "placeholder": 0, "completed": 0}

    for unit in script.units:
        unit_start = cursor
        shots = list(unit.shots or [])
        if not shots:
            duration = _positive_duration(unit.duration)
            timeline.append(_timeline_clip(
                script,
                unit,
                None,
                start=cursor,
                duration=duration,
                name=unit.outline or "待补画面",
                variant="stage",
                origin="script_placeholder",
            ))
            cursor += duration
            stats["placeholder"] += 1

        for shot in shots:
            target_duration = _positive_duration(shot.duration, _positive_duration(unit.duration))
            shot_start = cursor
            media = media_by_shot.get(shot.id)

            if media and media.get("kind") == "asset":
                source_duration = max(0.0, float(media.get("source_duration") or 0.0))
                if source_duration > 0:
                    matched_duration = min(target_duration, source_duration)
                    timeline.append(_timeline_clip(
                        script,
                        unit,
                        shot,
                        start=cursor,
                        duration=matched_duration,
                        name=media.get("name") or shot.description or "脚本匹配素材",
                        variant=media.get("variant") or "stage",
                        origin="script_match",
                        asset_id=media.get("asset_id"),
                        source_clip_id=media.get("source_clip_id"),
                        source_start=float(media.get("source_start") or 0.0),
                    ))
                    cursor += matched_duration
                    stats["matched"] += 1

                    remaining = target_duration - matched_duration
                    if remaining > 0.01:
                        timeline.append(_timeline_clip(
                            script,
                            unit,
                            shot,
                            start=cursor,
                            duration=remaining,
                            name=f"{shot.description or '分镜'} · 待补足 {remaining:.1f}s",
                            variant="stage",
                            origin="script_placeholder",
                        ))
                        cursor += remaining
                        stats["placeholder"] += 1
                    else:
                        cursor = shot_start + target_duration
                        stats["completed"] += 1
                    continue

            if media and media.get("kind") == "generated":
                timeline.append(_timeline_clip(
                    script,
                    unit,
                    shot,
                    start=cursor,
                    duration=target_duration,
                    name=media.get("name") or shot.description or "AI 生成分镜",
                    variant=media.get("variant") or "robot",
                    origin="script_generated",
                    generated_media_path=media.get("generated_media_path"),
                    generated_media_type=media.get("generated_media_type"),
                ))
                cursor += target_duration
                stats["generated"] += 1
                stats["completed"] += 1
                continue

            timeline.append(_timeline_clip(
                script,
                unit,
                shot,
                start=cursor,
                duration=target_duration,
                name=shot.description or unit.outline or "待补素材分镜",
                variant="stage",
                origin="script_placeholder",
            ))
            cursor += target_duration
            stats["placeholder"] += 1

        unit_duration = cursor - unit_start
        if unit.text and unit_duration > 0:
            timeline.append(_timeline_clip(
                script,
                unit,
                None,
                start=unit_start,
                duration=unit_duration,
                name=unit.outline or "字幕",
                variant="speaker",
                origin="script_subtitle",
                text=unit.text,
            ))

    return timeline, stats


@celery_app.task(bind=True, name="app.tasks.run_rough_cut")
def run_rough_cut(
    self,
    job_id: str,
    project_id: str,
    script_id: str,
    source_project_id: str,
    cut_version_id: str = "",
):
    """AI 初剪装配。"""
    try:
        run_async(
            _run_rough_cut_async(
                job_id, project_id, script_id, source_project_id, cut_version_id
            )
        )
    except Exception as error:
        run_async(_mark_rough_cut_failed(job_id, error))
        raise


async def _run_rough_cut_async(
    job_id: str,
    project_id: str,
    script_id: str,
    source_project_id: str,
    cut_version_id: str = "",
):
    from app.database import async_session_factory
    from app.models.script import Script, ScriptUnit, Shot
    from app.models.asset import Asset, Clip
    from app.models.project import Project
    from app.models.cut_version import CutVersion
    from app.models.job import Job
    from app.services.ai_provider import (
        generate_embedding,
        get_active_embedding_model,
        rerank_documents,
    )
    from app.config import get_settings
    from sqlalchemy import select, update, text
    from sqlalchemy.orm import selectinload

    stages = ["创建项目", "锁定统一视觉", "匹配真实素材与识别缺失镜头", "装配多轨初剪"]

    async with async_session_factory() as session:
        # 获取脚本和分镜
        result = await session.execute(
            select(Script)
            .where(Script.id == script_id)
            .options(selectinload(Script.units).selectinload(ScriptUnit.shots))
        )
        script = result.scalar_one_or_none()
        if not script:
            await _update_job_status(session, job_id, "FAILED", detail="脚本不存在")
            if cut_version_id:
                cut_version = await session.get(CutVersion, cut_version_id)
                if cut_version:
                    cut_version.status = "生成失败"
            await session.commit()
            return

        # Stage 0: 创建项目（已在 API 层完成）
        await _update_job_status(session, job_id, "RUNNING",
            stage=stages[0], stage_index=0, progress=15,
            detail="项目已创建")
        await session.commit()

        # Stage 1: 锁定统一视觉
        await _update_job_status(session, job_id, "RUNNING",
            stage=stages[1], stage_index=1, progress=30,
            detail=f"锁定视觉风格：{script.visual_config.get('stylePreset', 'brand-tech')}")
        await session.commit()

        # Stage 2: 匹配真实素材并标记缺失镜头；生成任务必须单独真实执行。
        await _update_job_status(session, job_id, "RUNNING",
            stage=stages[2], stage_index=2, progress=50,
            detail="正在匹配真实素材并识别待补齐镜头")
        await session.commit()

        matched_count = 0
        missing_shot_count = 0
        active_settings = get_settings()
        embedding_model = get_active_embedding_model()

        for unit in script.units:
            for shot in (unit.shots or []):
                if shot.selected_clip_id:
                    # 已有选定镜头
                    matched_count += 1
                    continue
                if (
                    shot.generated_video_path
                    or shot.generated_effect_video_path
                    or shot.generated_image_path
                ):
                    # 用户已经为该分镜生成了画面，装配阶段直接使用，不再用自动匹配覆盖。
                    continue

                # 尝试语义匹配
                query_text = f"{unit.outline} {unit.text} {shot.description}"
                try:
                    query_embedding = await generate_embedding(query_text)

                    # pgvector 检索
                    sql = text("""
                        SELECT c.id, c.title, c.transcript_segment, c.ocr_segment,
                               1 - (c.embedding <=> :embedding) as similarity
                        FROM clips c
                        JOIN assets a ON c.asset_id = a.id
                        WHERE a.project_id = :project_id
                          AND c.embedding IS NOT NULL
                          AND c.embedding_model = :embedding_model
                          AND c.embedding_dimensions = :embedding_dimensions
                          AND c.embedding_status = 'ready'
                        ORDER BY c.embedding <=> :embedding
                        LIMIT :candidate_limit
                    """)
                    result = await session.execute(sql, {
                        "embedding": str(query_embedding),
                        "project_id": source_project_id,
                        "embedding_model": embedding_model,
                        "embedding_dimensions": active_settings.ai_embedding_dimensions,
                        "candidate_limit": active_settings.ai_match_candidate_limit,
                    })
                    rows = result.fetchall()
                    row = rows[0] if rows else None
                    if rows and active_settings.has_rerank:
                        documents = [
                            " ".join(str(value or "").strip() for value in candidate[1:4]).strip()
                            for candidate in rows
                        ]
                        try:
                            reranked = await rerank_documents(query_text, documents)
                            row = rows[reranked[0]["index"]] if reranked else row
                        except Exception:
                            # Reranker 是真实向量召回后的增强项，不可用时保留真实向量排序。
                            row = rows[0]

                    if row and row[4] > 0.6:  # 保留真实向量相似度阈值
                        shot.selected_clip_id = row[0]
                        shot.status = "已选择"
                        unit.status = "已选择"
                        matched_count += 1
                    else:
                        shot.status = "待确认"
                        missing_shot_count += 1
                except Exception:
                    shot.status = "待编辑"
                    missing_shot_count += 1
                    # 匹配服务异常不应让整条脚本时间线消失；保留占位分镜供用户补齐。
                    continue

            # 更新单元状态
            if unit.shots and all(s.status == "已选择" for s in unit.shots):
                unit.status = "已选择"
            elif unit.shots and any(s.status == "已选择" for s in unit.shots):
                unit.status = "有候选"

        await session.commit()

        # Stage 3: 装配多轨初剪
        await _update_job_status(session, job_id, "RUNNING",
            stage=stages[3], stage_index=3, progress=80,
            detail="正在装配多轨初剪")
        await session.commit()

        media_by_shot: dict[str, dict] = {}
        for unit in script.units:
            for shot in (unit.shots or []):
                if shot.selected_clip_id:
                    clip = await session.get(Clip, shot.selected_clip_id)
                    asset = await session.get(Asset, clip.asset_id) if clip else None
                    if clip and asset and asset.file_path:
                        ranged_duration = float(clip.end_time or 0) - float(clip.start_time or 0)
                        source_duration = ranged_duration if ranged_duration > 0 else float(clip.duration or 0)
                        if source_duration > 0:
                            media_by_shot[shot.id] = {
                                "kind": "asset",
                                "asset_id": asset.id,
                                "source_clip_id": clip.id,
                                "source_start": float(clip.start_time or 0),
                                "source_duration": source_duration,
                                "name": clip.title or asset.name,
                                "variant": clip.variant or asset.variant or "stage",
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

        timeline, assembly_stats = _assemble_script_timeline(script, media_by_shot)
        if not any(item["track"] == "video" for item in timeline):
            await _update_job_status(
                session,
                job_id,
                "FAILED",
                stage="装配失败",
                detail="脚本中没有可用于装配时间线的内容",
                result=None,
                result_detail="请先为脚本添加脚本句或分镜",
            )
            if cut_version_id:
                cut_version = await session.get(CutVersion, cut_version_id)
                if cut_version:
                    cut_version.status = "生成失败"
            await session.commit()
            return

        matched_count = assembly_stats["matched"]
        generated_count = assembly_stats["generated"]
        missing_shot_count = assembly_stats["placeholder"]

        # 更新项目状态
        proj_result = await session.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        if project:
            project.status = "AI 初剪可编辑"
            project.description = (
                f"已按脚本时间线装配 {matched_count} 个真实素材镜头"
                + (f"、{generated_count} 个 AI 生成镜头" if generated_count else "")
                + (f"，仍有 {missing_shot_count} 处待补齐。" if missing_shot_count else "，可继续精剪并导出。")
            )
            project.ai_shot_count = generated_count
            project.timeline = timeline
            project.timeline_version = (project.timeline_version or 0) + 1
            project.timeline_updated_at = datetime.now(timezone.utc)

            cut_version = await session.get(CutVersion, cut_version_id) if cut_version_id else None
            if cut_version and cut_version.project_id == project.id:
                cut_version.status = "AI 初剪可编辑"
                cut_version.timeline = timeline
                cut_version.timeline_version = (cut_version.timeline_version or 0) + 1
                cut_version.timeline_updated_at = project.timeline_updated_at
                cut_version.aspect_ratio = project.aspect_ratio or cut_version.aspect_ratio

            from app.services.project_media import sync_project_media_items

            await sync_project_media_items(session, project, script)

        # 更新脚本状态
        script.status = "初剪可编辑"
        total_shots = sum(len(unit.shots or []) for unit in script.units)
        script.progress = round(assembly_stats["completed"] / total_shots * 100) if total_shots else 0
        script.summary = (
            f"已装配 {matched_count} 个真实素材镜头、{generated_count} 个 AI 生成镜头，"
            f"{missing_shot_count} 处待补齐。"
        )

        await session.commit()

        # 完成
        await _update_job_status(session, job_id, "SUCCEEDED",
            stage="完成", stage_index=3, progress=100,
            detail=(
                f"初剪已按完整脚本时间线装配：{matched_count} 个真实镜头，"
                f"{generated_count} 个 AI 镜头，{missing_shot_count} 处待补齐"
            ),
            result="打开时间线",
            result_detail="脚本分镜、素材、AI 画面和台词已写入时间线，可进入剪辑工作区补齐和精剪")
        await session.commit()


async def _update_job_status(session, job_id: str, status: str, **kwargs):
    """更新任务状态。"""
    from app.models.job import Job
    from sqlalchemy import update

    values = {"status": status, "updated_at": datetime.now(timezone.utc)}
    values.update(kwargs)
    await session.execute(update(Job).where(Job.id == job_id).values(**values))


@celery_app.task(bind=True, name="app.tasks.retry_rough_cut")
def retry_rough_cut(self, job_id: str):
    """重试初剪任务。"""
    try:
        run_async(_retry_rough_cut_async(job_id))
    except Exception as error:
        run_async(_mark_rough_cut_failed(job_id, error))
        raise


async def _mark_rough_cut_failed(job_id: str, error: Exception):
    from app.database import async_session_factory
    from app.models.cut_version import CutVersion
    from app.models.job import Job

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        version_id = (job.payload or {}).get("cut_version_id") if job else None
        if version_id:
            version = await session.get(CutVersion, version_id)
            if version:
                version.status = "生成失败"
        await _update_job_status(
            session,
            job_id,
            "FAILED",
            stage="初剪失败",
            detail=f"AI 初剪任务失败：{str(error)[:200]}",
            result=None,
            result_detail=str(error)[:200],
            result_url=None,
        )
        await session.commit()


async def _retry_rough_cut_async(job_id: str):
    from app.database import async_session_factory
    from app.models.job import Job
    from app.models.project import Project
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        # 优先使用任务创建时固定的快照，避免重试时误用其他版本的最新脚本。
        from app.models.script import Script
        payload = job.payload or {}
        script = await session.get(Script, payload.get("script_id")) if payload.get("script_id") else None
        if not script:
            script_result = await session.execute(
                select(Script)
                .where(Script.project_id == job.project_id, Script.is_snapshot.is_(True))
                .order_by(Script.created_at.desc())
            )
            script = script_result.scalars().first()
        if script:
            project = await session.get(Project, job.project_id)
            source_project_id = job.project_id
            if project and project.source_script_id:
                source_script = await session.get(Script, project.source_script_id)
                if source_script:
                    source_project_id = source_script.project_id
            await _run_rough_cut_async(
                job_id,
                job.project_id,
                script.id,
                payload.get("source_project_id", source_project_id),
                payload.get("cut_version_id", ""),
            )
