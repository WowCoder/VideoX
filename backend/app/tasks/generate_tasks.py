"""AI 生成 Celery 任务。

- AI 生图分镜（image）
- 图生视频（video）
- 示意特效（sketch）
"""

from datetime import datetime, timezone
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.tasks.celery_app import celery_app
from app.tasks.async_runner import run_async
from app.services.quotas import complete_job_success


def _persist_remote_media(remote_url: str, object_prefix: str, media_kind: str) -> str:
    """把第三方临时生成地址流式转存到自己的 MinIO，返回持久化对象 key。"""
    import httpx

    from app.utils.storage import upload_stream
    from app.utils.network_security import validate_external_media_url

    parsed = urlparse(remote_url)
    validate_external_media_url(remote_url)

    max_bytes = 50 * 1024 * 1024 if media_kind == "image" else 2 * 1024 * 1024 * 1024
    suffix = Path(parsed.path).suffix.lower()
    allowed_suffixes = {
        "image": {".jpg", ".jpeg", ".png", ".webp"},
        "video": {".mp4", ".mov", ".webm"},
    }[media_kind]
    if suffix not in allowed_suffixes:
        suffix = ".png" if media_kind == "image" else ".mp4"

    file_handle = tempfile.NamedTemporaryFile(prefix="openvma_ai_", suffix=suffix, delete=False)
    local_path = file_handle.name
    file_handle.close()
    try:
        total = 0
        content_type = "application/octet-stream"
        with httpx.Client(
            timeout=httpx.Timeout(300.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
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
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as error:
                        raise RuntimeError(
                            f"AI 媒体下载失败：HTTP {error.response.status_code}"
                        ) from None
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    expected_prefix = "image/" if media_kind == "image" else "video/"
                    if not content_type.startswith(expected_prefix):
                        raise RuntimeError(f"AI 服务返回的不是有效{media_kind}文件")
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
        return object_name
    except httpx.RequestError as error:
        raise RuntimeError(f"AI 媒体下载失败：{type(error).__name__}") from None
    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass


def _provider_media_url(path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    from app.utils.storage import get_file_url

    return get_file_url(path_or_url, expires_hours=1)


async def _mark_unexpected_failure(job_id: str, task_name: str, error: Exception) -> None:
    """把 Worker 最外层未捕获异常同步回任务，避免永久停留在 RUNNING。"""
    if not job_id:
        return

    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import update

    async with async_session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"]))
            .values(
                status="FAILED",
                stage="执行异常",
                detail=f"{task_name}任务执行异常：{str(error)[:200]}",
                result=None,
                result_detail="Worker 遇到未预期错误，请检查服务日志后重试",
                result_url=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


def _run_job(coro, job_id: str, task_name: str) -> None:
    try:
        run_async(coro)
    except Exception as error:
        try:
            run_async(_mark_unexpected_failure(job_id, task_name, error))
        except Exception:
            # 数据库本身不可用时保留原异常，让 Celery 正确记录任务失败。
            pass
        raise


async def _record_generation(
    session,
    shot,
    *,
    job_id: str,
    kind: str,
    storage_path: str,
    prompt: str,
):
    """保存一次不可变生成结果，并仅在分镜没有任何已选画面时自动采用。"""
    from app.models.script import ShotGeneration
    from sqlalchemy import select

    generation = None
    if job_id:
        generation = (
            await session.execute(
                select(ShotGeneration).where(
                    ShotGeneration.job_id == job_id,
                    ShotGeneration.kind == kind,
                )
            )
        ).scalar_one_or_none()

    should_select = not (
        shot.selected_clip_id
        or shot.generated_image_path
        or shot.generated_video_path
        or shot.generated_effect_video_path
    )
    if generation is None:
        generation = ShotGeneration(
            shot_id=shot.id,
            job_id=job_id or None,
            kind=kind,
            storage_path=storage_path,
            prompt=prompt,
            is_selected=should_select,
        )
        session.add(generation)
    else:
        # Celery 重投同一任务时保持同一条历史记录，避免重复候选。
        generation.storage_path = storage_path
        generation.prompt = prompt

    if should_select:
        shot.generated_image_path = storage_path if kind == "image" else None
        shot.generated_video_path = storage_path if kind == "video" else None
        shot.generated_effect_video_path = storage_path if kind == "effect" else None
        shot.visual_mode = {"image": "image", "video": "video", "effect": "sketch"}[kind]
        shot.status = "已选择"
    else:
        shot.status = "待确认"

    await session.flush()
    return generation


@celery_app.task(bind=True, name="app.tasks.generate_image_shot")
def generate_image_shot(self, shot_id: str, job_id: str = "", prompt: str = ""):
    """AI 生图分镜。

    阶段：理解分镜 → 生成构图 → 筛选关键帧 → 写入脚本
    """
    _run_job(_generate_image_async(shot_id, job_id, prompt), job_id, "AI 生图")


async def _generate_image_async(shot_id: str, job_id: str, prompt: str):
    from app.database import async_session_factory
    from app.models.script import Shot
    from app.models.job import Job
    from app.services.ai_provider import generate_image
    from sqlalchemy import select, update

    stages = ["理解分镜", "生成构图", "筛选关键帧", "写入脚本"]

    async with async_session_factory() as session:
        result = await session.execute(select(Shot).where(Shot.id == shot_id))
        shot = result.scalar_one_or_none()
        if not shot:
            if job_id:
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="FAILED", stage="分镜不存在", detail="目标分镜已被删除",
                        result=None, result_detail="无法继续生成", result_url=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            return

        final_prompt = prompt or shot.description or shot.notes or "科技感场景"

        for i, stage in enumerate(stages):
            if job_id:
                progress = int((i + 1) / len(stages) * 100)
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="RUNNING",
                        stage=stage,
                        stage_index=i,
                        progress=progress,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

            if i == 1:  # 生成构图阶段，调用 AI 生图
                try:
                    image_url = await generate_image(final_prompt)
                    job = await session.get(Job, job_id) if job_id else None
                    project_id = job.project_id if job else "unassigned"
                    generated_path = await __import__("asyncio").to_thread(
                        _persist_remote_media,
                        image_url,
                        f"generated/{project_id}/{shot.id}/images",
                        "image",
                    )
                except Exception as e:
                    shot.status = "待编辑"
                    if job_id:
                        await session.execute(
                            update(Job).where(
                                Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                            ).values(
                                status="FAILED",
                                stage="生成失败",
                                detail=f"AI 生图失败：{str(e)[:200]}",
                                result=None,
                                result_detail=str(e)[:200],
                                result_url=None,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                    await session.commit()
                    return

        generation = await _record_generation(
            session,
            shot,
            job_id=job_id,
            kind="image",
            storage_path=generated_path,
            prompt=final_prompt,
        )
        if job_id:
            completed = await complete_job_success(
                session,
                job_id,
                values={
                    "progress": 100,
                    "stage": "完成",
                    "detail": "已生成新的 AI 分镜候选",
                    "result": "打开脚本",
                    "result_detail": (
                        "AI 分镜图已生成并自动采用"
                        if generation.is_selected
                        else "AI 分镜图已加入历史候选，请确认后采用"
                    ),
                    "result_url": _provider_media_url(generated_path),
                },
            )
            if not completed:
                await session.rollback()
                return
        await session.commit()


@celery_app.task(bind=True, name="app.tasks.generate_video_shot")
def generate_video_shot(self, shot_id: str, job_id: str = "", prompt: str = ""):
    """图生视频。

    阶段：读取分镜图 → 解析运镜 → 生成视频 → 加入粗剪候选
    """
    _run_job(_generate_video_async(shot_id, job_id, prompt), job_id, "AI 视频生成")


async def _generate_video_async(shot_id: str, job_id: str, prompt: str):
    from app.database import async_session_factory
    from app.models.script import Shot, ShotGeneration
    from app.models.job import Job
    from app.services.ai_provider import (
        generate_video,
        query_video_task,
        video_task_failure_message,
    )
    from sqlalchemy import select, update
    import asyncio as aio

    stages = ["读取分镜图", "解析运镜", "生成视频", "加入粗剪候选"]

    async with async_session_factory() as session:
        result = await session.execute(select(Shot).where(Shot.id == shot_id))
        shot = result.scalar_one_or_none()
        if not shot:
            if job_id:
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="FAILED", stage="分镜不存在", detail="目标分镜已被删除",
                        result=None, result_detail="无法继续生成", result_url=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            return

        for i, stage in enumerate(stages):
            if job_id:
                progress = int((i + 1) / len(stages) * 100)
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="RUNNING",
                        stage=stage,
                        stage_index=i,
                        progress=progress,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

            if i == 2:  # 生成视频
                try:
                    image_url = shot.generated_image_path or (
                        await session.execute(
                            select(ShotGeneration.storage_path)
                            .where(
                                ShotGeneration.shot_id == shot.id,
                                ShotGeneration.kind == "image",
                            )
                            .order_by(ShotGeneration.created_at.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none() or ""
                    if not image_url:
                        raise RuntimeError("当前分镜没有可用于图生视频的关键帧")
                    task_id = await generate_video(
                        prompt or shot.description,
                        image_url=_provider_media_url(image_url),
                        duration=shot.duration,
                    )
                    video_url = ""
                    for _ in range(60):
                        task_result = await query_video_task(task_id)
                        task_status = task_result.get("output", {}).get("task_status")
                        if task_status == "SUCCEEDED":
                            video_url = task_result.get("output", {}).get("video_url", "")
                            break
                        if task_status == "FAILED":
                            raise RuntimeError(
                                video_task_failure_message(
                                    task_result,
                                    "AI 视频生成任务失败",
                                    "首帧图片",
                                )
                            )
                        await aio.sleep(5)
                    if not video_url:
                        raise RuntimeError("AI 视频生成超时或未返回视频地址")
                    job = await session.get(Job, job_id) if job_id else None
                    project_id = job.project_id if job else "unassigned"
                    generated_path = await aio.to_thread(
                        _persist_remote_media,
                        video_url,
                        f"generated/{project_id}/{shot.id}/videos",
                        "video",
                    )
                except Exception as e:
                    if job_id:
                        await session.execute(
                            update(Job).where(
                                Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                            ).values(
                                status="FAILED",
                                stage="生成失败",
                                detail=f"AI 视频生成失败：{str(e)[:200]}",
                                result=None,
                                result_detail=str(e)[:200],
                                result_url=None,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                    await session.commit()
                    return

        final_prompt = prompt or shot.description
        generation = await _record_generation(
            session,
            shot,
            job_id=job_id,
            kind="video",
            storage_path=generated_path,
            prompt=final_prompt,
        )
        if job_id:
            completed = await complete_job_success(
                session,
                job_id,
                values={
                    "progress": 100,
                    "stage": "完成",
                    "detail": "已生成新的图生视频候选",
                    "result": "打开脚本",
                    "result_detail": (
                        "分镜视频已生成并自动采用"
                        if generation.is_selected
                        else "分镜视频已加入历史候选，请确认后采用"
                    ),
                    "result_url": _provider_media_url(generated_path),
                },
            )
            if not completed:
                await session.rollback()
                return
        await session.commit()


@celery_app.task(bind=True, name="app.tasks.generate_effect_shot")
def generate_effect_shot(
    self,
    shot_id: str,
    job_id: str = "",
    motion_description: str = "",
):
    """示意特效生成。

    阶段：识别示意图 → 理解运动轨迹 → 生成特效 → 加入粗剪
    """
    _run_job(
        _generate_effect_async(shot_id, job_id, motion_description),
        job_id,
        "示意特效生成",
    )


async def _generate_effect_async(shot_id: str, job_id: str, motion_description: str):
    from app.database import async_session_factory
    from app.models.script import Shot
    from app.models.job import Job
    from app.services.ai_provider import (
        generate_effect_video,
        query_video_task,
        video_task_failure_message,
    )
    from sqlalchemy import select, update
    import asyncio as aio

    stages = ["识别示意图", "理解运动轨迹", "生成特效", "加入粗剪"]

    async with async_session_factory() as session:
        result = await session.execute(select(Shot).where(Shot.id == shot_id))
        shot = result.scalar_one_or_none()
        if not shot:
            if job_id:
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="FAILED", stage="分镜不存在", detail="目标分镜已被删除",
                        result=None, result_detail="无法继续生成", result_url=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            return

        sketch_data = shot.sketch_data or ""
        if not sketch_data:
            if job_id:
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="FAILED",
                        stage="草图不存在",
                        detail="示意草图未保存或已被清除",
                        result=None,
                        result_detail="请重新绘制草图后再生成",
                        result_url=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            return

        for i, stage in enumerate(stages):
            if job_id:
                progress = int((i + 1) / len(stages) * 100)
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
                        status="RUNNING",
                        stage=stage,
                        stage_index=i,
                        progress=progress,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

            if i == 2:  # 生成特效
                try:
                    base_prompt = shot.description or shot.notes or "示意特效"
                    prompt = (
                        f"{base_prompt}。动效要求：{motion_description.strip()}"
                        if motion_description.strip()
                        else base_prompt
                    )
                    task_id = await generate_effect_video(prompt, sketch_data=sketch_data)
                    # 轮询等待完成（每 5 秒一次，最多 60 次 = 5 分钟）
                    succeeded = False
                    for _ in range(60):
                        task_result = await query_video_task(task_id)
                        task_status = task_result.get("output", {}).get("task_status")
                        if task_status == "SUCCEEDED":
                            video_url = task_result.get("output", {}).get("video_url", "")
                            if video_url:
                                job = await session.get(Job, job_id) if job_id else None
                                project_id = job.project_id if job else "unassigned"
                                generated_path = await aio.to_thread(
                                    _persist_remote_media,
                                    video_url,
                                    f"generated/{project_id}/{shot.id}/effects",
                                    "video",
                                )
                                succeeded = True
                            break
                        if task_status == "FAILED":
                            raise RuntimeError(
                                video_task_failure_message(
                                    task_result,
                                    "AI 特效生成任务失败",
                                    "示意草图",
                                )
                            )
                        await aio.sleep(5)
                    if not succeeded:
                        raise RuntimeError("AI 特效生成超时或未返回视频地址")
                except Exception as e:
                    if job_id:
                        await session.execute(
                            update(Job).where(
                                Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                            ).values(
                                status="FAILED",
                                stage="生成失败",
                                detail=f"AI 特效生成失败：{str(e)[:200]}",
                                result=None,
                                result_detail=str(e)[:200],
                                result_url=None,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                    await session.commit()
                    return

        generation = await _record_generation(
            session,
            shot,
            job_id=job_id,
            kind="effect",
            storage_path=generated_path,
            prompt=prompt,
        )

        if job_id:
            completed = await complete_job_success(
                session,
                job_id,
                values={
                    "progress": 100,
                    "stage": "完成",
                    "detail": "已生成新的示意特效候选",
                    "result": "打开脚本",
                    "result_detail": (
                        "特效视频已生成并自动采用"
                        if generation.is_selected
                        else "特效视频已加入历史候选，请确认后采用"
                    ),
                    "result_url": _provider_media_url(generated_path),
                },
            )
            if not completed:
                await session.rollback()
                return
        await session.commit()
