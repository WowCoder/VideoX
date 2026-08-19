"""项目镜头对全局素材片段的真实语义匹配任务。"""

from datetime import datetime, timezone

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.match_script_shots")
def match_script_shots(self, script_id: str, shot_ids: list[str], job_id: str):
    run_async(_match_script_shots_async(script_id, shot_ids, job_id))


async def _match_script_shots_async(
    script_id: str, shot_ids: list[str], job_id: str
) -> None:
    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.asset import AssetSegment
    from app.models.job import Job
    from app.models.project import Project, ProjectRevision
    from app.models.script import Candidate, Script, ScriptUnit, Shot, ShotMediaVersion
    from app.services.ai_provider import (
        generate_embedding,
        get_active_embedding_model,
        rerank_documents,
    )
    from app.services.quotas import complete_job_success
    from app.services.workspace import record_revision

    settings = get_settings()
    try:
        async with async_session_factory() as session:
            job = await session.get(Job, job_id)
            script = (
                await session.execute(
                    select(Script)
                    .where(Script.id == script_id)
                    .options(
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
            shots = [shot for scene in script.units for shot in scene.shots if shot.id in requested]
            if len(shots) != len(requested):
                raise RuntimeError("部分镜头已被删除")
            base_revision = int((job.payload or {}).get("base_revision", script.revision))
            if script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次匹配结果已过期")

            job.status = "RUNNING"
            job.stage = "语义检索"
            job.progress = 10
            await session.commit()

            embedding_model = get_active_embedding_model()
            selected_count = 0
            candidate_count = 0
            for index, shot in enumerate(shots):
                scene = shot.unit
                query_text = " ".join(
                    value.strip()
                    for value in (scene.outline, scene.narration_text, scene.intent, shot.description)
                    if value and value.strip()
                )
                await session.execute(delete(Candidate).where(Candidate.shot_id == shot.id))
                if not query_text:
                    shot.status = "editing"
                    continue
                query_embedding = await generate_embedding(query_text)
                rows = (
                    await session.execute(
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
                            "project_id": script.project_id,
                            "embedding_model": embedding_model,
                            "embedding_dimensions": settings.ai_embedding_dimensions,
                            "candidate_limit": settings.ai_match_candidate_limit,
                        },
                    )
                ).mappings().all()
                ranked = list(rows)
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
                ranked = ranked[: settings.ai_match_result_limit]
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
                            reason=_match_reason(scene, shot, row, score),
                            low_confidence=score < 70,
                        )
                    )
                    candidate_count += 1
                best = ranked[0] if ranked else None
                best_score = round(float(best["similarity"] or 0) * 100) if best else 0
                if best and best_score >= 70:
                    segment = await session.get(AssetSegment, best["id"])
                    shot.segment_id = segment.id
                    shot.asset_id = segment.asset_id
                    shot.source_start_ms = segment.start_ms
                    shot.source_end_ms = segment.end_ms
                    shot.status = "selected"
                    selected_count += 1
                else:
                    shot.status = "review"
                job.progress = 10 + round((index + 1) / max(1, len(shots)) * 75)
                job.stage = "候选排序"
                await session.flush()

            for scene in script.units:
                if scene.shots and all(shot.status == "selected" for shot in scene.shots):
                    scene.status = "ready"
                elif any(shot.status in {"selected", "review"} for shot in scene.shots):
                    scene.status = "review"
            script.revision += 1
            script.project.composition.revision = script.revision
            await session.flush()
            await record_revision(
                session,
                script.project,
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
                    "result_detail": f"自动选中 {selected_count} 个高置信度镜头，其余请人工确认",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()
            if not completed:
                return
    except Exception as exc:
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
    signals: list[str] = []
    if row.get("transcript"):
        signals.append("语音内容")
    if row.get("ocr_text"):
        signals.append("画面文字")
    if row.get("title"):
        signals.append("片段主题")
    signal_text = "、".join(signals) or "画面语义"
    return f"{signal_text}与“{shot.description or scene.outline}”匹配，语义分 {score}"
