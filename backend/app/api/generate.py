"""显式作用范围的 AI、匹配、主成片编译和导出操作。"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.job import Job
from app.models.project import Project
from app.models.script import ScriptUnit, Shot
from app.models.user import User
from app.schemas.job import JobOut
from app.schemas.project import ScopeSelection
from app.services.project_access import require_project_access
from app.services.quotas import QuotaExceededError, admit_job_quota
from app.services.task_dispatch import dispatch_project_task
from app.services.workspace import load_project_workspace, record_revision


router = APIRouter()


class ProjectOperationRequest(BaseModel):
    scope: ScopeSelection
    operation: Literal[
        "match_assets",
        "complete_shots",
        "generate_image",
        "generate_video",
        "generate_effect",
        "generate_script",
        "compose",
        "export",
    ]
    parameters: dict = Field(default_factory=dict)
    expected_revision: int = Field(..., ge=0)


class OperationJobsOut(BaseModel):
    jobs: list[JobOut]


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


@router.post("/projects/{project_id}/operations", response_model=OperationJobsOut, status_code=202)
async def execute_project_operation(
    project_id: str,
    request: ProjectOperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(project_id, user, db, "editor")
    project = await load_project_workspace(db, project_id, user.id, for_update=True)
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
    shot_ids = (
        _resolve_shot_ids(project, request.scope)
        if request.operation not in project_level_operations
        else []
    )
    if request.operation not in project_level_operations and not shot_ids:
        raise HTTPException(status_code=422, detail="当前作用范围内没有镜头")
    if request.operation in project_level_operations and request.scope.type != "project":
        raise HTTPException(status_code=422, detail="该操作只能作用于整个项目")

    jobs: list[Job] = []
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
                subject_type="project",
                subject_id=project.id,
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
                subject_type="project",
                subject_id=project.id,
                name="AI 完善分镜",
                type="AI 分镜完善",
                status="QUEUED",
                stage="等待生成",
                stages=["完善描述", "保存结果"],
                payload={"script_id": project.script.id, "shot_ids": shot_ids},
            )
        )
    elif request.operation in {"generate_image", "generate_video", "generate_effect"}:
        config = {
            "generate_image": ("AI 生图分镜", "ai_image", "prompt"),
            "generate_video": ("分镜图 AI 生视频", "ai_video", "prompt"),
            "generate_effect": ("示意图特效视频", "ai_video", "motion_description"),
        }[request.operation]
        for shot_id in shot_ids:
            job = Job(
                owner_id=user.id,
                project_id=project.id,
                subject_type="shot",
                subject_id=shot_id,
                name=config[0],
                type=config[0],
                status="QUEUED",
                stage="等待生成",
                stages=["提交生成", "等待结果", "保存素材"],
                payload={
                    "shot_id": shot_id,
                    config[2]: str(request.parameters.get(config[2]) or ""),
                },
            )
            try:
                await admit_job_quota(db, job, user.id, config[1], 1)
            except QuotaExceededError as exc:
                raise HTTPException(status_code=403, detail="当前会员生成额度不足") from exc
            jobs.append(job)
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
        try:
            await admit_job_quota(db, job, user.id, "export", 1)
        except QuotaExceededError as exc:
            raise HTTPException(status_code=403, detail="当前会员导出额度不足") from exc
        jobs.append(job)

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
        try:
            task = await _dispatch_job(db, project, job)
            job.celery_task_id = task.id
        except Exception as exc:
            job.status = "FAILED"
            job.stage = "派发失败"
            job.detail = f"任务派发失败：{str(exc)[:200]}"
    await db.commit()
    return OperationJobsOut(jobs=[JobOut.model_validate(job) for job in jobs])
