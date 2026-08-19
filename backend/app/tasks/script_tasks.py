"""项目脚本内容相关的显式 AI 任务。"""

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


def normalize_generated_script(raw: str, target_duration_seconds: int) -> list[dict]:
    """校验模型输出并归一化为可直接写入唯一 ProjectDocument 的场景/镜头。"""
    text_value = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    data = json.loads(text_value)
    scenes_value = data.get("scenes") if isinstance(data, dict) else data
    if not isinstance(scenes_value, list) or not scenes_value:
        raise RuntimeError("文本模型未返回合法的场景数组")

    scenes: list[dict] = []
    for scene_value in scenes_value[:12]:
        if not isinstance(scene_value, dict):
            continue
        shots_value = scene_value.get("shots")
        if not isinstance(shots_value, list) or not shots_value:
            shots_value = [{"description": scene_value.get("intent") or scene_value.get("outline") or "场景画面"}]
        shots: list[dict] = []
        for shot_value in shots_value[:8]:
            if not isinstance(shot_value, dict):
                continue
            description = str(shot_value.get("description") or "").strip()
            if not description:
                continue
            try:
                duration_seconds = float(shot_value.get("duration_seconds") or 0)
            except (TypeError, ValueError):
                duration_seconds = 0
            shots.append({
                "description": description[:5000],
                "weight": max(0.5, duration_seconds),
            })
        if not shots:
            continue
        scenes.append({
            "outline": str(scene_value.get("outline") or f"场景 {len(scenes) + 1}").strip()[:200],
            "narration_text": str(scene_value.get("narration") or scene_value.get("narration_text") or "").strip()[:10000],
            "intent": str(scene_value.get("intent") or "").strip()[:10000],
            "shots": shots,
        })
    if not scenes:
        raise RuntimeError("文本模型没有生成可用镜头")

    shots = [shot for scene in scenes for shot in scene["shots"]]
    target_ms = max(15_000, min(300_000, int(target_duration_seconds) * 1000))
    minimum_ms = min(1000, target_ms // len(shots))
    distributable_ms = max(0, target_ms - minimum_ms * len(shots))
    total_weight = sum(shot["weight"] for shot in shots) or len(shots)
    assigned_ms = 0
    for index, shot in enumerate(shots):
        if index == len(shots) - 1:
            duration_ms = target_ms - assigned_ms
        else:
            duration_ms = minimum_ms + round(distributable_ms * shot["weight"] / total_weight)
            assigned_ms += duration_ms
        shot["duration_ms"] = max(100, duration_ms)
        shot.pop("weight", None)
    for scene in scenes:
        scene["estimated_duration_ms"] = sum(shot["duration_ms"] for shot in scene["shots"])
    return scenes


@celery_app.task(bind=True, name="app.tasks.generate_project_script")
def generate_project_script(self, project_id: str, job_id: str):
    run_async(_generate_project_script_async(project_id, job_id))


async def _generate_project_script_async(project_id: str, job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.asset import Asset, ProjectAssetLink
    from app.models.job import Job
    from app.models.notification import Notification
    from app.models.project import Project
    from app.models.script import Script, ScriptUnit, Shot, ShotMediaVersion
    from app.models.user import User
    from app.services.ai_provider import generate_text
    from app.services.quotas import complete_job_success
    from app.services.workspace import record_revision
    from sqlalchemy.orm import selectinload

    try:
        async with async_session_factory() as session:
            job = await session.get(Job, job_id)
            project = (
                await session.execute(
                    select(Project)
                    .where(Project.id == project_id)
                    .options(
                        selectinload(Project.composition),
                        selectinload(Project.script)
                        .selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.candidates),
                        selectinload(Project.script)
                        .selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.media_versions)
                        .selectinload(ShotMediaVersion.asset),
                    )
                )
            ).scalar_one_or_none()
            if not job or not project or not project.script or not project.composition:
                raise RuntimeError("项目脚本或任务不存在")
            payload = job.payload or {}
            base_revision = int(payload.get("base_revision", project.script.revision))
            if project.script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次 AI 结果已过期")
            job.status = "RUNNING"
            job.stage = "理解目标"
            job.progress = 15
            await session.commit()

            asset_context: list[dict] = []
            if payload.get("include_asset_context", True):
                assets = (
                    await session.execute(
                        select(Asset)
                        .join(ProjectAssetLink, ProjectAssetLink.asset_id == Asset.id)
                        .where(
                            ProjectAssetLink.project_id == project_id,
                            Asset.deleted_at.is_(None),
                        )
                        .limit(30)
                    )
                ).scalars().all()
                asset_context = [
                    {
                        "name": asset.name,
                        "type": asset.media_type,
                        "transcript": (asset.transcript or "")[:1200],
                        "ocr": (asset.ocr_text or "")[:600],
                        "tags": (asset.tags or [])[:20],
                    }
                    for asset in assets
                ]

            duration_seconds = int(payload.get("duration_seconds") or 60)
            prompt = str(payload.get("prompt") or "").strip()
            tone = str(payload.get("tone") or "专业清晰")
            job.stage = "生成结构"
            job.progress = 35
            await session.commit()
            raw = await generate_text(
                prompt=f"""请为一个视频项目生成完整脚本结构。
创作目标：{prompt}
表达语气：{tone}
目标总时长：{duration_seconds} 秒
项目素材摘要：{json.dumps(asset_context, ensure_ascii=False)}

只返回合法 JSON：
{{"scenes":[{{"outline":"场景标题","narration":"旁白正文","intent":"画面意图","shots":[{{"description":"包含主体、景别/机位、动作、构图和光线的镜头描述","duration_seconds":5}}]}}]}}
要求：叙事完整、场景和镜头顺序可直接成片；不得捏造素材摘要中没有出现的具体人物、品牌数据或事实；总时长接近目标。""",
                system_prompt="你是专业视频编导，只输出合法 JSON，不输出 Markdown。",
                temperature=0.5,
                max_tokens=6000,
            )
            generated_scenes = normalize_generated_script(raw, duration_seconds)
            job.stage = "写入场景与镜头"
            job.progress = 75
            await session.commit()

            job = (
                await session.execute(
                    select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True)
                )
            ).scalar_one()
            if job.status not in {"QUEUED", "RUNNING"}:
                await session.rollback()
                return

            project = (
                await session.execute(
                    select(Project)
                    .where(Project.id == project_id)
                    .options(
                        selectinload(Project.composition),
                        selectinload(Project.script)
                        .selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.candidates),
                        selectinload(Project.script)
                        .selectinload(Script.units)
                        .selectinload(ScriptUnit.shots)
                        .selectinload(Shot.media_versions)
                        .selectinload(ShotMediaVersion.asset),
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            script = project.script
            if script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次 AI 结果已过期")

            script.units.clear()
            for scene_index, scene_value in enumerate(generated_scenes):
                scene = ScriptUnit(
                    index=scene_index,
                    outline=scene_value["outline"],
                    narration_text=scene_value["narration_text"],
                    intent=scene_value["intent"],
                    status="editing",
                    estimated_duration_ms=scene_value["estimated_duration_ms"],
                    revision=1,
                )
                for shot_index, shot_value in enumerate(scene_value["shots"]):
                    scene.shots.append(Shot(
                        index=shot_index,
                        description=shot_value["description"],
                        status="editing",
                        source_start_ms=0,
                        source_end_ms=shot_value["duration_ms"],
                        duration_ms=shot_value["duration_ms"],
                        subtitle_text=scene_value["narration_text"],
                        subtitle_source_revision=1,
                        revision=1,
                        candidates=[],
                        media_versions=[],
                    ))
                script.units.append(scene)

            script.summary = prompt
            script.status = "editing"
            script.source_type = "ai"
            script.target_duration_seconds = duration_seconds
            script.estimated_duration_seconds = round(
                sum(scene["estimated_duration_ms"] for scene in generated_scenes) / 1000
            )
            script.revision += 1
            project.composition.revision = script.revision
            project.composition.global_scopes = {
                **(project.composition.global_scopes or {}),
                "scenes": {},
            }
            project.composition.visual_layers = {
                "items": [
                    item for item in (project.composition.visual_layers or {}).get("items", [])
                    if item.get("scope") != "scene" and not item.get("sceneId")
                ]
            }
            project.composition.workflow_graph = {"nodes": [], "edges": []}
            project.composition.timeline = {"duration_ms": 0, "tracks": []}
            project.composition.current_render_asset_id = None
            project.master_output_asset_id = None
            project.status = "editing"
            await session.flush()
            await record_revision(
                session,
                project,
                job.owner_id,
                "ai_result",
                {"job_id": job.id, "operation": "generate_script"},
            )
            scene_count = len(generated_scenes)
            shot_count = sum(len(scene["shots"]) for scene in generated_scenes)
            completed = await complete_job_success(
                session,
                job.id,
                values={
                    "stage": "完成",
                    "progress": 100,
                    "detail": f"已生成 {scene_count} 个场景、{shot_count} 个镜头",
                    "result": "打开项目",
                    "result_detail": f"AI 脚本已写入当前项目 · {duration_seconds} 秒 · {tone}",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            if not completed:
                await session.rollback()
                return
            user = await session.get(User, job.owner_id)
            existing_notification = (
                await session.execute(
                    select(Notification.id).where(
                        Notification.job_id == job.id,
                        Notification.type == "script_generation",
                    )
                )
            ).scalar_one_or_none()
            if user and user.notify_script_generation and not existing_notification:
                session.add(Notification(
                    user_id=job.owner_id,
                    project_id=project.id,
                    job_id=job.id,
                    type="script_generation",
                    title="AI 脚本生成完成",
                    message=f"{project.name} 已生成 {scene_count} 个场景、{shot_count} 个镜头",
                    link=f"/workspace/projects/{project.id}",
                ))
            await session.commit()
    except Exception as exc:
        logger.exception("AI project script generation failed for job %s", job_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
                .values(
                    status="FAILED",
                    stage="脚本生成失败",
                    detail=str(exc)[:500],
                    result=None,
                    result_detail=str(exc)[:500],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()


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
    from app.models.project import Project
    from app.models.script import Script, ScriptUnit, Shot, ShotMediaVersion
    from app.services.ai_provider import generate_text
    from app.services.quotas import complete_job_success
    from app.services.workspace import record_revision

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
                raise RuntimeError("项目已继续编辑，本次 AI 结果已过期")
            job.status = "RUNNING"
            job.stage = "完善描述"
            job.progress = 25
            await session.commit()

            inputs = [
                {
                    "id": shot.id,
                    "outline": shot.unit.outline,
                    "narration": shot.unit.narration_text,
                    "intent": shot.unit.intent,
                    "description": shot.description,
                    "duration_ms": shot.duration_ms,
                }
                for shot in shots
            ]
            raw = await generate_text(
                prompt=f"""请完善以下视频分镜描述。只能基于给定旁白、画面意图和已有描述，
不得捏造人物、产品、地点或事件。每个描述包含主体、景别/机位、动作和光线。
严格返回 JSON 数组：[{{"id":"shot-id","description":"完善后的描述"}}]
输入：{json.dumps(inputs, ensure_ascii=False)}""",
                system_prompt="你是专业视频分镜师，只输出合法 JSON。",
                temperature=0.4,
                max_tokens=3000,
            )
            text_value = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            result = json.loads(text_value)
            if not isinstance(result, list):
                raise RuntimeError("文本模型未返回合法的分镜数组")
            descriptions = {
                str(item.get("id")): str(item.get("description") or "").strip()
                for item in result
                if isinstance(item, dict) and item.get("id") and item.get("description")
            }
            for shot in shots:
                description = descriptions.get(shot.id)
                if description:
                    shot.description = description
                    shot.status = "editing"
                    shot.revision += 1
            script.revision += 1
            script.project.composition.revision = script.revision
            await session.flush()
            await record_revision(
                session,
                script.project,
                job.owner_id,
                "ai_result",
                {"job_id": job.id, "operation": "complete_shots"},
            )
            await complete_job_success(
                session,
                job.id,
                values={
                    "stage": "完成",
                    "progress": 100,
                    "detail": f"已完善 {len(descriptions)} 个镜头描述",
                    "result": "打开项目",
                    "result_detail": "分镜描述已写入项目",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()
    except Exception as exc:
        async with async_session_factory() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
                .values(
                    status="FAILED",
                    stage="完善失败",
                    detail=str(exc)[:500],
                    result=None,
                    result_detail=str(exc)[:500],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
