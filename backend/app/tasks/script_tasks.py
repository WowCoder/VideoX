"""脚本内容相关的显式 AI 任务。"""

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.complete_shot_descriptions")
def complete_shot_descriptions(
    self, script_id: str, shot_ids: list[str], job_id: str
):
    run_async(_complete_shot_descriptions_async(script_id, shot_ids, job_id))


async def _complete_shot_descriptions_async(
    script_id: str, shot_ids: list[str], job_id: str
) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.models.script import Candidate, ScriptUnit, Shot
    from app.services.ai_provider import generate_text

    try:
        async with async_session_factory() as session:
            shots = list(
                (
                    await session.execute(
                        select(Shot)
                        .join(ScriptUnit, Shot.unit_id == ScriptUnit.id)
                        .where(
                            ScriptUnit.script_id == script_id,
                            Shot.id.in_(shot_ids),
                        )
                        .options(selectinload(Shot.unit))
                    )
                ).scalars().all()
            )
            if len(shots) != len(set(shot_ids)):
                raise RuntimeError("部分分镜已被删除，无法继续完善")
            await session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="RUNNING",
                    stage="完善描述",
                    stage_index=1,
                    progress=30,
                    detail=f"正在完善 {len(shots)} 个分镜描述",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

            inputs = [
                {
                    "id": shot.id,
                    "outline": shot.unit.outline,
                    "dialogue": shot.unit.text,
                    "intent": shot.unit.intent,
                    "description": shot.description,
                    "duration": shot.duration,
                }
                for shot in shots
            ]
            prompt = f"""请完善以下视频分镜描述。只能基于给定台词、画面意图和已有描述，不得捏造人物、产品、地点或事件。
每个描述应包含主体、景别/机位、动作和光线，保持简洁且可执行。严格返回 JSON 数组：
[{{"id":"shot-id","description":"完善后的描述"}}]

输入：
{json.dumps(inputs, ensure_ascii=False)}"""
            raw = await generate_text(
                prompt=prompt,
                system_prompt="你是专业视频分镜师，只输出合法 JSON，不输出 Markdown。",
                temperature=0.4,
                max_tokens=3000,
            )
            text = raw.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            result = json.loads(text.strip())
            if not isinstance(result, list):
                raise RuntimeError("文本模型未返回合法的分镜数组")
            descriptions = {
                str(item.get("id")): str(item.get("description") or "").strip()
                for item in result
                if isinstance(item, dict) and item.get("id") and item.get("description")
            }
            await session.execute(delete(Candidate).where(Candidate.shot_id.in_(shot_ids)))
            for shot in shots:
                description = descriptions.get(shot.id)
                if description:
                    shot.description = description
                    shot.status = "待编辑"
                    shot.selected_clip_id = None
                    shot.candidates = []
                    shot.unit.status = "待编辑"
                    shot.unit.selected_clip_id = None
                    shot.unit.candidates = []

            await session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="SUCCEEDED",
                    stage="完成",
                    stage_index=2,
                    progress=100,
                    detail=f"已完善 {len(descriptions)} 个分镜描述",
                    result="打开脚本",
                    result_detail="分镜描述已写入脚本，请检查后重新匹配素材",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as error:
        async with async_session_factory() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="FAILED",
                    stage="完善失败",
                    detail=f"AI 分镜完善失败：{str(error)[:200]}",
                    result=None,
                    result_detail=str(error)[:200],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
