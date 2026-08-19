"""唯一主成片编译任务；不再创建脚本快照或 CutVersion。"""

from datetime import datetime, timezone

from sqlalchemy import update

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.run_rough_cut")
def run_rough_cut(self, job_id: str, project_id: str):
    try:
        run_async(_run_rough_cut_async(job_id, project_id))
    except Exception as exc:
        run_async(_mark_failed(job_id, exc))
        raise


async def _run_rough_cut_async(job_id: str, project_id: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from app.services.quotas import complete_job_success
    from app.services.workspace import load_project_workspace, record_revision

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        if not job:
            raise RuntimeError("主成片任务不存在")
        project = await load_project_workspace(
            session, project_id, job.owner_id, for_update=True
        )
        base_revision = int((job.payload or {}).get("base_revision", project.script.revision))
        if project.script.revision != base_revision:
            raise RuntimeError("项目已继续编辑，本次主成片编排基线已过期")
        job.status = "RUNNING"
        job.stage = "检查镜头"
        job.progress = 20
        await session.commit()

        total = 0
        matched = 0
        generated = 0
        missing = 0
        total_duration_ms = 0
        for scene in project.script.units:
            scene_missing = 0
            if not scene.shots and scene.narration_text:
                missing += 1
                scene_missing += 1
            scene_duration = 0
            for shot in scene.shots:
                total += 1
                scene_duration += shot.duration_ms
                total_duration_ms += shot.duration_ms
                selected_version = next(
                    (
                        item
                        for item in shot.media_versions
                        if item.id == shot.selected_media_version_id or item.is_selected
                    ),
                    None,
                )
                if selected_version:
                    generated += 1
                elif shot.asset_id:
                    matched += 1
                else:
                    missing += 1
                    scene_missing += 1
                if not shot.subtitle_overridden:
                    shot.subtitle_text = scene.narration_text
                    shot.subtitle_source_revision = scene.revision
            scene.estimated_duration_ms = scene_duration
            if scene.shots and scene_missing == 0:
                scene.status = "ready"

        if total == 0:
            raise RuntimeError("项目没有镜头，不能生成主成片")
        job.stage = "编排主成片"
        job.progress = 70
        project.script.estimated_duration_seconds = round(total_duration_ms / 1000)
        project.script.status = "ready" if missing == 0 else "editing"
        project.status = "ready" if missing == 0 else "editing"
        project.description = (
            f"主成片已编排：{matched} 个素材镜头、{generated} 个 AI 镜头"
            + (f"，还有 {missing} 个镜头待补齐" if missing else "，可以预览或导出")
        )
        project.script.revision += 1
        project.composition.revision = project.script.revision
        project.composition.render_settings = {
            **(project.composition.render_settings or {}),
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "shot_count": total,
            "duration_ms": total_duration_ms,
            "missing_shot_count": missing,
        }
        await session.flush()
        await record_revision(
            session,
            project,
            job.owner_id,
            "ai_result",
            {"job_id": job.id, "operation": "compose"},
        )
        await complete_job_success(
            session,
            job.id,
            values={
                "stage": "完成",
                "progress": 100,
                "detail": project.description,
                "result": "打开项目",
                "result_detail": "主成片已由项目唯一脚本和镜头设置编译完成",
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await session.commit()


async def _mark_failed(job_id: str, error: Exception) -> None:
    from app.database import async_session_factory
    from app.models.job import Job

    async with async_session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
            .values(
                status="FAILED",
                stage="主成片编排失败",
                detail=str(error)[:500],
                result=None,
                result_detail=str(error)[:500],
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


@celery_app.task(bind=True, name="app.tasks.retry_rough_cut")
def retry_rough_cut(self, job_id: str):
    run_async(_retry_rough_cut_async(job_id))


async def _retry_rough_cut_async(job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        if job and job.project_id:
            await _run_rough_cut_async(job.id, job.project_id)
