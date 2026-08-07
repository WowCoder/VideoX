"""镜头匹配 Celery 任务。

基于脚本单元语义 → pgvector 向量检索 → 返回候选 + 评分 + 解释。
"""

import logging
from typing import Optional

from app.tasks.celery_app import celery_app
from app.tasks.async_runner import run_async

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.match_shots")
def match_shots(self, script_id: str, unit_id: str, job_id: str = ""):
    """为脚本单元匹配候选镜头。

    1. 获取单元文本
    2. 生成 embedding
    3. pgvector 相似度检索
    4. 写入候选列表
    """
    run_async(_match_shots_async(script_id, unit_id, job_id))


@celery_app.task(bind=True, name="app.tasks.match_script_units")
def match_script_units(self, script_id: str, unit_ids: list[str], job_id: str):
    """兼容旧任务：把脚本单元解析为分镜后使用新的 Shot 级匹配。"""
    run_async(_match_script_units_async(script_id, unit_ids, job_id))


@celery_app.task(bind=True, name="app.tasks.match_script_shots")
def match_script_shots(self, script_id: str, shot_ids: list[str], job_id: str):
    """按具体分镜匹配候选，避免同一脚本单元的多个镜头共享相同结果。"""
    run_async(_match_script_shots_async(script_id, shot_ids, job_id))


async def _match_script_units_async(script_id: str, unit_ids: list[str], job_id: str):
    from app.database import async_session_factory
    from app.models.script import Shot
    from sqlalchemy import select

    async with async_session_factory() as session:
        shot_ids = list(
            (
                await session.execute(
                    select(Shot.id)
                    .where(Shot.unit_id.in_(unit_ids))
                    .order_by(Shot.unit_id, Shot.index)
                )
            ).scalars().all()
        )
    await _match_script_shots_async(script_id, shot_ids, job_id)


async def _match_script_shots_async(script_id: str, shot_ids: list[str], job_id: str):
    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import update
    from datetime import datetime, timezone

    try:
        total_candidates = 0
        if not shot_ids:
            raise RuntimeError("脚本中没有可匹配的分镜")
        for index, shot_id in enumerate(shot_ids):
            async with async_session_factory() as session:
                await session.execute(
                    update(Job).where(Job.id == job_id).values(
                        status="RUNNING",
                        stage="检索素材",
                        stage_index=1,
                        progress=int(index / max(len(shot_ids), 1) * 90),
                        detail=f"正在匹配第 {index + 1}/{len(shot_ids)} 个分镜",
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            total_candidates += await _match_shot_async(script_id, shot_id)

        async with async_session_factory() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="SUCCEEDED",
                    stage="匹配完成",
                    stage_index=2,
                    progress=100,
                    detail=(
                        f"已检查 {len(shot_ids)} 个分镜，"
                        f"找到 {total_candidates} 个真实候选镜头"
                    ),
                    result="打开脚本",
                    result_detail=(
                        "镜头候选已写入脚本"
                        if total_candidates
                        else "未找到满足条件的真实候选镜头"
                    ),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as error:
        async with async_session_factory() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="FAILED",
                    stage="匹配失败",
                    detail=f"镜头匹配失败：{str(error)[:200]}",
                    result=None,
                    result_detail=str(error)[:200],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()


def _fmt_time(sec: float) -> str:
    """格式化秒数为 MM:SS。"""
    total = int(sec or 0)
    return f"{total // 60:02d}:{total % 60:02d}"


async def _match_shot_async(script_id: str, shot_id: str):
    from app.database import async_session_factory
    from app.models.script import ScriptUnit, Shot, Candidate, Script
    from app.models.asset import Asset, Clip
    from app.services.ai_provider import (
        generate_embedding,
        get_active_embedding_model,
        rerank_documents,
    )
    from app.config import get_settings
    from sqlalchemy import delete, select, text
    from datetime import datetime, timezone
    import uuid

    async with async_session_factory() as session:
        shot_result = await session.execute(select(Shot).where(Shot.id == shot_id))
        shot = shot_result.scalar_one_or_none()
        if not shot:
            return 0

        # 获取单元
        result = await session.execute(select(ScriptUnit).where(ScriptUnit.id == shot.unit_id))
        unit = result.scalar_one_or_none()
        if not unit:
            return 0

        # 获取脚本对应的项目
        script_result = await session.execute(select(Script).where(Script.id == script_id))
        script = script_result.scalar_one_or_none()
        if not script:
            return 0

        # 生成查询向量
        query_text = " ".join(
            value.strip()
            for value in (unit.outline, unit.text, unit.intent, shot.description)
            if value and value.strip()
        )
        if not query_text:
            raise RuntimeError("分镜缺少可用于匹配的台词或画面描述")
        query_embedding = await generate_embedding(query_text)
        active_settings = get_settings()
        embedding_model = get_active_embedding_model()

        # 统一候选数据结构
        candidates_data: list[dict] = []

        if query_embedding:
            # pgvector 语义检索
            sql = text("""
                SELECT c.id AS clip_id, c.title, c.start_time, c.end_time, c.duration,
                       c.transcript_segment, c.ocr_segment, c.scene_type, c.shot_type,
                       c.camera_motion, c.persons, c.objects, c.variant,
                       c.quality_score, c.thumbnail_path, a.name AS asset_name,
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
                "project_id": script.project_id,
                "embedding_model": embedding_model,
                "embedding_dimensions": active_settings.ai_embedding_dimensions,
                "candidate_limit": active_settings.ai_match_candidate_limit,
            })
            vector_candidates = [dict(row) for row in result.mappings().all()]
            if vector_candidates:
                documents = [
                    " ".join(
                        str(value).strip()
                        for value in (
                            row.get("title"),
                            row.get("transcript_segment"),
                            row.get("ocr_segment"),
                            row.get("scene_type"),
                            row.get("shot_type"),
                        )
                        if value and str(value).strip()
                    )
                    for row in vector_candidates
                ]
                try:
                    reranked = await rerank_documents(query_text, documents)
                    for item in reranked[: active_settings.ai_match_result_limit]:
                        candidate = vector_candidates[item["index"]]
                        candidate["rerank_score"] = item.get("relevance_score")
                        candidates_data.append(candidate)
                except Exception as error:
                    logger.warning("本地 Reranker 不可用，保留真实向量排序：%s", error)
                    candidates_data = vector_candidates[: active_settings.ai_match_result_limit]
        else:
            raise RuntimeError("语义匹配服务未返回有效向量")

        # 每次真实匹配只覆盖当前 Shot 的旧候选。
        await session.execute(delete(Candidate).where(Candidate.shot_id == shot_id))

        # 创建候选记录，同时同步到 ScriptUnit/Shot 的 JSON 字段。
        # Desktop 编辑器读取的是嵌套的 candidates 数组；只写规范化表会导致
        # 任务显示成功，但编辑器仍看不到任何候选。
        candidate_payloads: list[dict] = []
        for data in candidates_data:
            similarity = float(data["similarity"] or 0.0)
            score = max(0, min(100, round(similarity * 100)))
            candidate_id = f"cand-{uuid.uuid4().hex[:12]}"

            candidate = Candidate(
                id=candidate_id,
                shot_id=shot_id,
                unit_id=unit.id,
                clip_id=data["clip_id"],
                title=data["title"],
                source=data["asset_name"] or "",
                range_start=_fmt_time(data["start_time"]),
                range_end=_fmt_time(data["end_time"]),
                score=score,
                reason=_generate_match_reason(unit, data, similarity),
                variant=data["variant"] or "stage",
                low_confidence=score < 70,
            )
            session.add(candidate)
            candidate_payloads.append({
                "id": candidate_id,
                "shot_id": shot_id,
                "unit_id": unit.id,
                "clip_id": data["clip_id"],
                "title": data["title"],
                "source": data["asset_name"] or "",
                "range_start": _fmt_time(data["start_time"]),
                "range_end": _fmt_time(data["end_time"]),
                "score": score,
                "reason": _generate_match_reason(unit, data, similarity),
                "variant": data["variant"] or "stage",
                "low_confidence": score < 70,
                "thumbnail_path": data.get("thumbnail_path"),
            })

        shot.candidates = candidate_payloads
        if candidate_payloads and shot.status == "待编辑":
            shot.status = "待确认"

        unit_shots = list((
            await session.execute(
                select(Shot).where(Shot.unit_id == unit.id).order_by(Shot.index)
            )
        ).scalars().all())
        if unit_shots and all(item.status == "已选择" for item in unit_shots):
            unit.status = "已选择"
        elif any(item.status in {"已选择", "待确认"} or item.candidates for item in unit_shots):
            unit.status = "有候选"
        else:
            unit.status = "待编辑"
        unit.candidates = candidate_payloads

        await session.commit()
        return len(candidates_data)


async def _match_shots_async(script_id: str, unit_id: str, job_id: str):
    """兼容旧的单单元任务入口。"""
    from app.database import async_session_factory
    from app.models.script import Shot
    from sqlalchemy import select

    async with async_session_factory() as session:
        shot_ids = list(
            (
                await session.execute(
                    select(Shot.id).where(Shot.unit_id == unit_id).order_by(Shot.index)
                )
            ).scalars().all()
        )
    total = 0
    for shot_id in shot_ids:
        total += await _match_shot_async(script_id, shot_id)
    return total


def _generate_match_reason(unit, clip_data: dict, similarity: float) -> str:
    """生成匹配原因说明。"""
    reasons = []
    if similarity and similarity > 0.8:
        reasons.append("语义高度匹配")
    elif similarity and similarity > 0.6:
        reasons.append("语义相关")
    else:
        reasons.append("部分相关")

    if clip_data.get("scene_type"):
        reasons.append(f"场景：{clip_data['scene_type']}")
    if clip_data.get("shot_type"):
        reasons.append(f"镜头：{clip_data['shot_type']}")
    if clip_data.get("rerank_score") is not None:
        reasons.append("已通过语义重排")

    return "，".join(reasons)
