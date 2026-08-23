"""项目镜头对全局素材片段的真实语义匹配任务。"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import raiseload, selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.match_script_shots")
def match_script_shots(self, script_id: str, shot_ids: list[str], job_id: str):
    run_async(_match_script_shots_async(script_id, shot_ids, job_id))


async def _match_script_shots_async(
    script_id: str, shot_ids: list[str], job_id: str
) -> None:
    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.job import Job
    from app.models.project import Project
    from app.models.script import Candidate, Script, ScriptUnit, Shot, ShotMediaVersion
    from app.services.ai_provider import (
        generate_embedding,
        get_active_embedding_model,
        rerank_documents,
    )
    from app.services.quotas import complete_job_success
    from app.services.workspace import load_project_workspace, record_revision

    settings = get_settings()
    try:
        base_revision = -1
        project_id = ""
        shot_contexts: list[dict] = []
        async with async_session_factory() as session:
            job = await session.get(Job, job_id)
            script = (
                await session.execute(
                    select(Script)
                    .where(Script.id == script_id)
                    .options(
                        raiseload("*"),
                        selectinload(Script.project).selectinload(Project.composition),
                        selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.candidates),
                        selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.media_versions)
                        .selectinload(ShotMediaVersion.asset),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not job or not script:
                raise RuntimeError("项目脚本或任务不存在")
            requested = set(shot_ids)
            shot_contexts = [
                {
                    "shot_id": shot.id,
                    "outline": scene.outline,
                    "narration": scene.narration_text,
                    "intent": scene.intent,
                    "description": shot.description,
                }
                for scene in script.units
                for shot in scene.shots
                if shot.id in requested
            ]
            if len(shot_contexts) != len(requested):
                raise RuntimeError("部分镜头已被删除")
            base_revision = int((job.payload or {}).get("base_revision", script.revision))
            if script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次匹配结果已过期")
            project_id = script.project_id

            job.status = "RUNNING"
            job.stage = "语义检索"
            job.progress = 10
            await session.commit()

        # 向量化和重排都是外部 IO。这一阶段只保留纯数据上下文，
        # 不持有 ORM 对象、项目行锁或跨网络调用的数据库事务。
        embedding_model = get_active_embedding_model()
        ranked_by_shot: dict[str, list[dict]] = {}
        for index, context in enumerate(shot_contexts):
            query_text = " ".join(
                str(value).strip()
                for value in (
                    context["outline"],
                    context["narration"],
                    context["intent"],
                    context["description"],
                )
                if value and str(value).strip()
            )
            ranked: list[dict] = []
            if query_text:
                query_embedding = await generate_embedding(query_text)
                async with async_session_factory() as read_session:
                    rows = (
                        await read_session.execute(
                            text(
                                """
                                SELECT seg.id, seg.asset_id, seg.title, seg.transcript, seg.ocr_text,
                                       seg.start_ms, seg.end_ms,
                                       1 - (seg.embedding <=> :embedding) AS similarity,
                                       a.name
                                FROM asset_segments seg
                                JOIN assets a ON a.id = seg.asset_id
                                JOIN project_asset_links pal ON pal.asset_id = a.id
                                WHERE pal.project_id = :project_id
                                  AND a.deleted_at IS NULL
                                  AND a.media_type IN ('image', 'video')
                                  AND seg.embedding IS NOT NULL
                                  AND seg.embedding_model = :embedding_model
                                  AND seg.embedding_dimensions = :embedding_dimensions
                                  AND seg.embedding_status = 'ready'
                                ORDER BY seg.embedding <=> :embedding
                                LIMIT :candidate_limit
                                """
                            ),
                            {
                                "embedding": str(query_embedding),
                                "project_id": project_id,
                                "embedding_model": embedding_model,
                                "embedding_dimensions": settings.ai_embedding_dimensions,
                                "candidate_limit": settings.ai_match_candidate_limit,
                            },
                        )
                    ).mappings().all()
                    ranked = [dict(row) for row in rows]
            if ranked and settings.has_rerank:
                documents = [
                    " ".join(
                        str(item.get(key) or "").strip()
                        for key in ("title", "transcript", "ocr_text")
                    )
                    for item in ranked
                ]
                try:
                    reranked = await rerank_documents(query_text, documents)
                    ranked = [ranked[item["index"]] for item in reranked]
                except Exception:
                    pass
            ranked_by_shot[str(context["shot_id"])] = ranked[: settings.ai_match_result_limit]
            async with async_session_factory() as progress_session:
                await progress_session.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
                    .values(
                        progress=10 + round((index + 1) / max(1, len(shot_contexts)) * 75),
                        stage="候选排序",
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await progress_session.commit()

        # 结果全部准备完成后再重新锁定项目并写入。如果生成期间
        # 项目继续编辑，整批结果作废，避免用旧描述的匹配覆盖新内容。
        async with async_session_factory() as session:
            job = (
                await session.execute(
                    select(Job)
                    .where(Job.id == job_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if not job:
                raise RuntimeError("项目脚本或任务不存在")
            if job.status not in {"QUEUED", "RUNNING"}:
                await session.rollback()
                return
            project = await load_project_workspace(
                session,
                project_id,
                job.owner_id,
                for_update=True,
            )
            script = project.script
            if script.id != script_id:
                raise RuntimeError("项目脚本已变更")
            if script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次匹配结果已过期")
            requested = set(shot_ids)
            contexts_by_id = {str(item["shot_id"]): item for item in shot_contexts}
            shots = [
                shot
                for scene in script.units
                for shot in scene.shots
                if shot.id in requested
            ]
            if len(shots) != len(requested):
                raise RuntimeError("部分镜头已被删除")

            candidate_count = 0
            for shot in shots:
                await session.execute(delete(Candidate).where(Candidate.shot_id == shot.id))
                ranked = ranked_by_shot.get(shot.id, [])
                context = contexts_by_id[shot.id]
                for row in ranked:
                    score = max(0, min(100, round(float(row["similarity"] or 0) * 100)))
                    session.add(
                        Candidate(
                            shot_id=shot.id,
                            segment_id=row["id"],
                            title=row["title"] or row["name"],
                            source=row["name"],
                            range_start_ms=int(row["start_ms"] or 0),
                            range_end_ms=int(row["end_ms"] or 0),
                            score=score,
                            reason=_match_reason_text(
                                str(context["description"]),
                                str(context["outline"]),
                                row,
                                score,
                            ),
                            low_confidence=score < 70,
                        )
                    )
                    candidate_count += 1
                # 匹配任务只保存候选，不自动替换当前素材。无论分数多高，
                # 都由用户在镜头面板中预览并显式选择。
                shot.status = "review"

            for scene in script.units:
                if scene.shots and all(shot.status == "selected" for shot in scene.shots):
                    scene.status = "ready"
                elif any(shot.status in {"selected", "review"} for shot in scene.shots):
                    scene.status = "review"
            script.revision += 1
            project.composition.revision = script.revision
            await session.flush()
            await record_revision(
                session,
                project,
                job.owner_id,
                "ai_result",
                {"job_id": job.id, "operation": "match_assets"},
            )
            completed = await complete_job_success(
                session,
                job.id,
                values={
                    "stage": "完成",
                    "progress": 100,
                    "detail": f"已为 {len(shots)} 个镜头生成 {candidate_count} 个候选",
                    "result": "打开项目",
                    "result_detail": "候选已生成，当前素材未改变，请在镜头面板中选择",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()
            if not completed:
                return
    except Exception as exc:
        logger.exception("镜头素材匹配任务失败 job_id=%s script_id=%s", job_id, script_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
                .values(
                    status="FAILED",
                    stage="匹配失败",
                    detail=str(exc)[:500],
                    result=None,
                    result_detail=str(exc)[:500],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()


def _match_reason(scene, shot, row: dict, score: int) -> str:
    return _match_reason_text(shot.description, scene.outline, row, score)


def _match_reason_text(description: str, outline: str, row: dict, score: int) -> str:
    signals: list[str] = []
    if row.get("transcript"):
        signals.append("语音内容")
    if row.get("ocr_text"):
        signals.append("画面文字")
    if row.get("title"):
        signals.append("片段主题")
    signal_text = "、".join(signals) or "画面语义"
    return f"{signal_text}与“{description or outline}”匹配，语义分 {score}"
