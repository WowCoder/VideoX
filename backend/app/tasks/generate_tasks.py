"""镜头 AI 图片、视频和示意特效生成任务。"""

from datetime import datetime, timezone
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.services.quotas import complete_job_success
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


def _can_auto_select_media_version(current_revision: int, base_revision: int) -> bool:
    """Only an AI result based on the still-current shot may replace that shot's media."""
    return current_revision == base_revision


def _persist_remote_media(
    remote_url: str, object_prefix: str, media_kind: str
) -> tuple[str, int, str]:
    """安全下载第三方临时结果并转存到自己的对象存储。"""
    import httpx

    from app.utils.network_security import validate_external_media_url
    from app.utils.storage import upload_stream

    parsed = urlparse(remote_url)
    validate_external_media_url(remote_url)
    max_bytes = 50 * 1024 * 1024 if media_kind == "image" else 2 * 1024 * 1024 * 1024
    suffix = Path(parsed.path).suffix.lower()
    allowed = {
        "image": {".jpg", ".jpeg", ".png", ".webp"},
        "video": {".mp4", ".mov", ".webm"},
    }[media_kind]
    if suffix not in allowed:
        suffix = ".png" if media_kind == "image" else ".mp4"
    handle = tempfile.NamedTemporaryFile(prefix="openvma_ai_", suffix=suffix, delete=False)
    local_path = handle.name
    handle.close()
    try:
        total = 0
        content_type = "application/octet-stream"
        with httpx.Client(timeout=httpx.Timeout(300.0), follow_redirects=False, trust_env=False) as client:
            current_url = remote_url
            for redirect_count in range(4):
                validate_external_media_url(current_url)
                with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count == 3:
                            raise RuntimeError("AI 媒体下载发生了无效或过多的重定向")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    prefix = "image/" if media_kind == "image" else "video/"
                    if not content_type.startswith(prefix):
                        raise RuntimeError("AI 服务返回的媒体类型不正确")
                    with open(local_path, "wb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise RuntimeError("AI 生成文件超过允许的持久化大小")
                            output.write(chunk)
                    break
        if total <= 0:
            raise RuntimeError("AI 服务返回了空文件")
        object_name = f"{object_prefix}/{uuid.uuid4().hex}{suffix}"
        with open(local_path, "rb") as stream:
            upload_stream(object_name, stream, total, content_type)
        return object_name, total, content_type
    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass


async def _mark_failure(job_id: str, label: str, error: Exception) -> None:
    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import update

    async with async_session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
            .values(
                status="FAILED",
                stage="生成失败",
                detail=f"{label}失败：{str(error)[:300]}",
                result=None,
                result_detail=str(error)[:500],
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


def _run(coro, job_id: str, label: str) -> None:
    try:
        run_async(coro)
    except Exception as exc:
        run_async(_mark_failure(job_id, label, exc))
        raise


@celery_app.task(bind=True, name="app.tasks.generate_image_shot")
def generate_image_shot(self, shot_id: str, job_id: str = "", prompt: str = ""):
    _run(_generate_media(shot_id, job_id, "image", prompt), job_id, "AI 生图")


@celery_app.task(bind=True, name="app.tasks.generate_video_shot")
def generate_video_shot(self, shot_id: str, job_id: str = "", prompt: str = ""):
    _run(_generate_media(shot_id, job_id, "video", prompt), job_id, "AI 视频")


@celery_app.task(bind=True, name="app.tasks.generate_effect_shot")
def generate_effect_shot(
    self, shot_id: str, job_id: str = "", motion_description: str = ""
):
    _run(
        _generate_media(shot_id, job_id, "effect", motion_description),
        job_id,
        "示意特效视频",
    )


async def _generate_media(
    shot_id: str,
    job_id: str,
    kind: str,
    requested_prompt: str,
) -> None:
    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.asset import Asset, AssetSegment, ProjectAssetLink
    from app.models.job import Job
    from app.models.script import Shot, ShotMediaVersion
    from app.services.ai_provider import generate_effect_video, generate_image, generate_video
    from app.services.workspace import ensure_shot_material_history, load_project_workspace, record_revision
    from app.services.storage_usage import recalculate_storage_usage
    from sqlalchemy import select

    settings = get_settings()
    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        project_id = (
            await session.execute(
                select(Job.project_id).where(Job.id == job_id)
            )
        ).scalar_one_or_none()
        if not job or not project_id:
            raise RuntimeError("生成任务或项目不存在")
        project = await load_project_workspace(session, project_id, job.owner_id, for_update=True)
        shot = next(
            (item for scene in project.script.units for item in scene.shots if item.id == shot_id),
            None,
        )
        scene = next(
            (item for item in project.script.units if any(candidate.id == shot_id for candidate in item.shots)),
            None,
        )
        if not shot:
            raise RuntimeError("镜头不存在")
        base_revision = int((job.payload or {}).get("base_revision", project.script.revision))
        base_shot_revision = int((job.payload or {}).get("base_shot_revision", shot.revision))
        if shot.revision != base_shot_revision:
            raise RuntimeError("当前镜头已继续编辑，本次生成结果已过期")
        job.status = "RUNNING"
        job.stage = "提交生成"
        job.progress = 10
        await session.commit()

        # 使用已加载的 scene -> shots 方向，避免 AsyncSession 在
        # shot.unit 上发起隐式 lazy IO 而触发 MissingGreenlet。
        prompt = requested_prompt.strip() or shot.description.strip() or (scene.intent.strip() if scene else "")
        if not prompt:
            raise RuntimeError("镜头缺少可用于生成的画面描述")
        source_snapshot = {
            "asset_id": shot.asset_id,
            "selected_media_version_id": shot.selected_media_version_id,
            "visual_mode": shot.visual_mode,
            "source_start_ms": shot.source_start_ms,
            "source_end_ms": shot.source_end_ms,
            "transform": shot.transform or {},
            "adjust": shot.adjust or {},
            "motion": shot.motion or {},
        }
        if kind == "image":
            ratio = project.composition.aspect_ratio
            size = {
                "16:9": "1280*720",
                "9:16": "720*1280",
                "1:1": "1024*1024",
                "4:3": "1024*768",
            }.get(ratio, "1280*720")
            remote_url = await generate_image(prompt=prompt, size=size)
            media_type = "image"
            media_kind = "generated_image"
            provider_name = settings.ai_image_provider
            provider_model = settings.active_image_model
        elif kind == "video":
            image_source = ""
            if shot.asset_id:
                source_asset = await session.get(Asset, shot.asset_id)
                if source_asset and source_asset.media_type == "image" and source_asset.file_path:
                    # Provider 层各自准备首帧：DashScope 上传临时 OSS，Agnes
                    # 对私有对象执行图生图公网中转；任务层不耦合供应商协议。
                    image_source = source_asset.file_path
            remote_url = await generate_video(
                prompt=prompt,
                image_url=image_source,
                duration=max(2, min(15, round(shot.duration_ms / 1000))),
                aspect_ratio=project.composition.aspect_ratio,
            )
            media_type = "video"
            media_kind = "generated_video"
            provider_name = (
                settings.ai_image_to_video_provider
                if image_source
                else settings.ai_text_to_video_provider
            )
            provider_model = (
                settings.active_image_to_video_model
                if image_source
                else settings.active_text_to_video_model
            )
        else:
            if not shot.sketch_data:
                raise RuntimeError("示意特效视频需要先保存 Canvas 草图")
            remote_url = await generate_effect_video(prompt=prompt, sketch_data=shot.sketch_data)
            media_type = "video"
            media_kind = "effect_video"
            provider_name = settings.ai_effect_video_provider
            provider_model = settings.ai_effect_video_model

        job.stage = "保存素材"
        job.progress = 75
        await session.commit()
        storage_path, storage_bytes, content_type = _persist_remote_media(
            remote_url,
            f"generated/{project.id}/{shot.id}/{media_type}",
            media_type,
        )

        # 外部生成期间初始事务早已提交并释放项目锁。写入结果前必须重新锁定
        # 项目并刷新整个聚合，否则多个并发镜头会从同一个旧 revision 递增，
        # 最终撞上 uq_project_revision_number。
        project = await load_project_workspace(
            session,
            project_id,
            job.owner_id,
            for_update=True,
        )
        shot = next(
            (
                item
                for scene in project.script.units
                for item in scene.shots
                if item.id == shot_id
            ),
            None,
        )
        if not shot:
            raise RuntimeError("镜头已被删除，本次生成结果无法写入项目")

        asset = Asset(
            owner_id=job.owner_id,
            name=f"{shot.description or 'AI 生成镜头'}-{kind}",
            media_type=media_type,
            source_type="ai_generated",
            status="ready",
            processing_status="ready",
            mime_type=content_type,
            file_path=storage_path,
            preview_path=storage_path,
            thumbnail_path=storage_path if media_type == "image" else None,
            file_size_mb=round(storage_bytes / (1024 * 1024), 2),
            duration_ms=0 if media_type == "image" else shot.duration_ms,
            has_audio=False,
            ai_provider=provider_name,
            ai_model=provider_model,
            ai_prompt=prompt,
            asset_metadata={"shot_id": shot.id, "job_id": job.id, "operation": kind},
        )
        session.add(asset)
        await session.flush()
        session.add(
            AssetSegment(
                asset_id=asset.id,
                start_ms=0,
                end_ms=asset.duration_ms,
                title=asset.name,
                thumbnail_path=asset.thumbnail_path,
            )
        )
        session.add(
            ProjectAssetLink(
                project_id=project.id,
                asset_id=asset.id,
                role="shot_media",
                linked_by=job.owner_id,
            )
        )
        await session.refresh(shot, attribute_names=["revision"])
        selected = _can_auto_select_media_version(shot.revision, base_shot_revision)
        if selected:
            ensure_shot_material_history(
                shot,
                asset_id=shot.asset_id,
                segment_id=shot.segment_id,
                source_start_ms=shot.source_start_ms,
                source_end_ms=shot.source_end_ms,
                origin="previous_selection",
                operation="previous_selection",
                selected=False,
            )
            for existing_version in shot.media_versions:
                existing_version.is_selected = False
        version = ShotMediaVersion(
            shot=shot,
            asset=asset,
            job_id=job.id,
            parent_version_id=shot.selected_media_version_id,
            kind=media_kind,
            operation=kind,
            parameters={
                "prompt": prompt,
                "source_snapshot": source_snapshot,
                "base_revision": base_revision,
                "base_shot_revision": base_shot_revision,
                "stale_result": not selected,
                "material_history": {
                    "segment_id": None,
                    "source_start_ms": 0,
                    "source_end_ms": asset.duration_ms,
                    "origin": "ai_image" if media_type == "image" else "ai_video",
                    "last_used_at": datetime.now(timezone.utc).isoformat() if selected else None,
                },
            },
            status="ready",
            is_selected=selected,
        )
        session.add(version)
        await session.flush()
        await recalculate_storage_usage(session, job.owner_id)
        if selected:
            shot.selected_media_version_id = version.id
            shot.asset_id = asset.id
            shot.segment_id = None
            shot.source_start_ms = 0
            shot.source_end_ms = asset.duration_ms
        shot.revision += 1
        project.script.revision += 1
        project.composition.revision = project.script.revision
        await session.flush()
        await record_revision(
            session,
            project,
            job.owner_id,
            "ai_result",
            {"job_id": job.id, "operation": kind, "asset_id": asset.id},
        )
        await complete_job_success(
            session,
            job.id,
            values={
                "stage": "完成",
                "progress": 100,
                "detail": "AI 媒体已生成并进入全局素材库",
                "result": "打开项目",
                "result_detail": "已自动采用首个生成版本；后续版本保留为候选",
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await session.commit()
