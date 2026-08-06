"""素材路由：上传/列表/详情/片段。"""

import asyncio
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Text, cast, desc, exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.asset import Asset, Clip
from app.models.job import Job
from app.models.script import Script
from app.services.project_access import accessible_project_condition, require_project_access
from app.schemas.asset import AssetOut, AssetListOut, ClipOut, UploadResponse
from app.config import get_settings
from app.utils.storage import get_file_url, upload_stream

router = APIRouter()
settings = get_settings()


_CONTAINER_EXTENSIONS = {
    "mp4": {".mp4", ".mov", ".m4v", ".m4a"},
    "matroska": {".mkv", ".webm"},
    "avi": {".avi"},
    "wav": {".wav"},
    "flac": {".flac"},
    "ogg": {".ogg", ".oga", ".opus"},
    "mp3": {".mp3"},
    "aac": {".aac"},
}
_CONTAINER_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "matroska": "video/x-matroska",
    "avi": "video/x-msvideo",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "aac": "audio/aac",
}


def _safe_filename(filename: str | None) -> str:
    """去除路径和控制字符，同时尽量保留用户可辨识的文件名。"""
    basename = Path(filename or "未命名素材.mp4").name.strip()
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", basename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = "未命名素材.mp4"
    stem = Path(cleaned).stem[:160] or "未命名素材"
    suffix = Path(cleaned).suffix.lower()[:12]
    return f"{stem}{suffix}"


def _detect_container(header: bytes) -> str | None:
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "mp4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "matroska"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "avi"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF6) == 0xF0:
        return "aac"
    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    ):
        return "mp3"
    return None


def _file_size(upload: UploadFile) -> int:
    reported_size = getattr(upload, "size", None)
    if isinstance(reported_size, int):
        return reported_size
    stream = upload.file
    current = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current)
    return size


def _validate_upload_size(file_size: int, max_size_gb: int | None = None) -> None:
    """校验单文件大小；GiB 使用 1024³ 字节精确定义。"""
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    size_limit_gb = settings.max_upload_size_gb if max_size_gb is None else max_size_gb
    max_size_bytes = size_limit_gb * 1024 * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"单个文件不能超过 {size_limit_gb} GiB",
        )


def _probe_upload_stream(upload: UploadFile) -> dict:
    """直接探测 Starlette 的临时文件，不把完整媒体读入内存。"""
    stream = upload.file
    stream.seek(0)
    file_descriptor = stream.fileno()  # SpooledTemporaryFile 会在需要时落盘。
    stream.seek(0)
    probe_path = f"/dev/fd/{file_descriptor}"
    result = subprocess.run(
        [
            settings.ffprobe_path,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            probe_path,
        ],
        pass_fds=(file_descriptor,),
        capture_output=True,
        text=True,
        timeout=60,
    )
    stream.seek(0)
    if result.returncode != 0:
        raise HTTPException(status_code=415, detail="媒体文件无法解析，请检查文件是否完整或编码是否受支持")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=415, detail="无法读取媒体信息") from exc
    streams = data.get("streams", [])
    has_video = any(item.get("codec_type") == "video" for item in streams)
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    if not has_video and not has_audio:
        raise HTTPException(status_code=415, detail="文件中没有可用的视频轨或音频轨")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise HTTPException(status_code=415, detail="媒体时长无效或文件尚未完整写入")
    audio_stream = next(
        (item for item in streams if item.get("codec_type") == "audio"),
        {},
    )
    data["openvma"] = {
        "media_type": "video" if has_video else "audio",
        "has_audio": has_audio,
        "duration": duration,
        "audio_codec": audio_stream.get("codec_name"),
        "sample_rate": int(audio_stream.get("sample_rate") or 0) or None,
        "channels": int(audio_stream.get("channels") or 0) or None,
        "bitrate": int(audio_stream.get("bit_rate") or 0) or None,
    }
    return data


def _clip_out(clip: Clip) -> ClipOut:
    thumbnail_url = get_file_url(clip.thumbnail_path) if clip.thumbnail_path else None
    return ClipOut.model_validate(clip).model_copy(
        update={"thumbnail_url": thumbnail_url}
    )


def _match_excerpt(value: str | None, needle: str, context: int = 36) -> str | None:
    """返回真实命中文本附近的短摘要，不生成或补写任何内容。"""
    text_value = (value or "").strip()
    if not text_value:
        return None
    index = text_value.casefold().find(needle.casefold())
    if index < 0:
        return None
    start = max(0, index - context)
    end = min(len(text_value), index + len(needle) + context)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text_value) else ""
    return f"{prefix}{text_value[start:end].strip()}{suffix}"


def _asset_match_meta(asset: Asset, search: str) -> dict:
    needle = search.strip()
    if not needle:
        return {"match_field": None, "match_excerpt": None, "matched_clip_id": None}

    checks = (
        ("name", asset.name, None),
        ("tag", " / ".join(str(tag) for tag in (asset.tags or [])), None),
        ("transcript", asset.transcript, None),
        ("ocr", asset.ocr_text, None),
    )
    for field, value, clip_id in checks:
        excerpt = _match_excerpt(value, needle)
        if excerpt:
            return {"match_field": field, "match_excerpt": excerpt, "matched_clip_id": clip_id}

    for clip in asset.clips:
        for field, value in (
            ("clip_title", clip.title),
            ("clip_transcript", clip.transcript_segment),
            ("clip_ocr", clip.ocr_segment),
        ):
            excerpt = _match_excerpt(value, needle)
            if excerpt:
                return {
                    "match_field": field,
                    "match_excerpt": excerpt,
                    "matched_clip_id": clip.id,
                }
    return {"match_field": None, "match_excerpt": None, "matched_clip_id": None}


def _asset_out(asset: Asset, search: str = "") -> AssetOut:
    playable_path = asset.preview_path or asset.file_path
    media_url = get_file_url(playable_path) if playable_path else None
    thumbnail_url = get_file_url(asset.thumbnail_path) if asset.thumbnail_path else None
    return AssetOut.model_validate(asset).model_copy(
        update={
            "media_url": media_url,
            "thumbnail_url": thumbnail_url,
            "clips": [_clip_out(clip) for clip in asset.clips],
            **_asset_match_meta(asset, search),
        }
    )


@router.get("", response_model=AssetListOut)
async def list_assets(
    project_id: str = Query("", description="按项目筛选"),
    media_type: str = Query("", description="按媒体类型筛选：video / audio"),
    search: str = Query("", description="搜索名称、标签、转写、OCR 和片段文本"),
    status_filter: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取素材列表。"""
    query = select(Asset).join(Project).where(accessible_project_condition(user.id))

    if project_id:
        query = query.where(Asset.project_id == project_id)
    if media_type:
        if media_type not in {"video", "audio"}:
            raise HTTPException(status_code=422, detail="媒体类型仅支持 video 或 audio")
        query = query.where(Asset.media_type == media_type)
    if search:
        keyword = f"%{search.strip()}%"
        clip_text_match = exists(
            select(1).where(
                Clip.asset_id == Asset.id,
                or_(
                    Clip.title.ilike(keyword),
                    Clip.transcript_segment.ilike(keyword),
                    Clip.ocr_segment.ilike(keyword),
                ),
            )
        )
        query = query.where(
            or_(
                Asset.name.ilike(keyword),
                Asset.transcript.ilike(keyword),
                Asset.ocr_text.ilike(keyword),
                cast(Asset.tags, Text).ilike(keyword),
                clip_text_match,
            )
        )
    if status_filter:
        query = query.where(Asset.status == status_filter)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(desc(Asset.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .options(selectinload(Asset.clips))
    )
    result = await db.execute(query)
    assets = result.scalars().all()

    return AssetListOut(items=[_asset_out(a, search) for a in assets], total=total)


@router.post("/upload", response_model=UploadResponse)
async def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传素材文件。

    文件上传到 MinIO，创建 Asset 记录，派发媒体处理任务。
    """
    project = (await require_project_access(project_id, user, db, "editor")).project
    billing_user = (
        await db.execute(
            select(User)
            .where(User.id == project.owner_id)
            .options(selectinload(User.membership), selectinload(User.usage))
        )
    ).scalar_one()

    safe_name = _safe_filename(file.filename)
    file_size = await asyncio.to_thread(_file_size, file)
    _validate_upload_size(file_size)

    await file.seek(0)
    header = await file.read(64)
    await file.seek(0)
    container = _detect_container(header)
    if not container:
        raise HTTPException(
            status_code=415,
            detail="仅支持真实的视频或 MP3、WAV、M4A、AAC、FLAC、OGG 音频文件",
        )
    suffix = Path(safe_name).suffix.lower()
    if suffix not in _CONTAINER_EXTENSIONS[container]:
        raise HTTPException(status_code=415, detail="文件扩展名与真实视频容器格式不一致")

    probe_data = await asyncio.to_thread(_probe_upload_stream, file)
    media_info = probe_data["openvma"]

    file_size_mb = file_size / (1024 * 1024)
    storage_used_mb = (
        await db.execute(
            select(func.coalesce(func.sum(Asset.file_size_mb), 0.0))
            .join(Project)
            .where(Project.owner_id == project.owner_id)
        )
    ).scalar() or 0.0
    storage_limit_mb = (billing_user.membership.storage_gb if billing_user.membership else 5) * 1024
    if storage_used_mb + file_size_mb > storage_limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"存储空间不足：当前剩余约 {max(0, storage_limit_mb - storage_used_mb):.1f}MB",
        )

    # 使用 MinIO multipart 流式上传，避免 await file.read() 将大文件整体放入内存。
    object_name = f"assets/{project_id}/{uuid.uuid4().hex}/{safe_name}"
    await file.seek(0)
    try:
        await asyncio.to_thread(
            upload_stream,
            object_name,
            file.file,
            file_size,
            (
                "audio/mp4"
                if media_info["media_type"] == "audio" and container == "mp4"
                else _CONTAINER_CONTENT_TYPES[container]
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"对象存储写入失败：{str(exc)[:160]}") from exc
    finally:
        await file.seek(0)

    # 创建 Asset
    asset = Asset(
        project_id=project_id,
        name=safe_name,
        duration=0.0,
        status="处理中",
        source="用户上传",
        variant=project.variant,
        media_type=media_info["media_type"],
        has_audio=media_info["has_audio"],
        file_path=object_name,
        file_size_mb=round(file_size_mb, 2),
        audio_codec=media_info["audio_codec"],
        sample_rate=media_info["sample_rate"],
        channels=media_info["channels"],
        bitrate=media_info["bitrate"],
    )
    db.add(asset)
    await db.flush()

    # 更新项目素材计数
    project.asset_count = (project.asset_count or 0) + 1
    if project.status == "等待上传":
        project.status = "处理中"

    # 创建处理任务
    job = Job(
        project_id=project_id,
        name=f"素材处理：{safe_name}",
        type="素材处理",
        status="QUEUED",
        stage="等待处理",
        stages=(
            ["音频标准化", "提取音频信息", "完成"]
            if media_info["media_type"] == "audio"
            else ["转码", "语音转写(ASR)", "画面文字识别(OCR)", "镜头切分", "语义索引"]
        ),
        stage_index=0,
        progress=0,
        eta="预计 2-5 分钟",
        detail=f"{safe_name} 已进入处理队列",
        result=None,
        result_detail="",
        payload={"asset_id": asset.id},
        is_simulated=False,
    )
    db.add(job)
    await db.flush()

    if billing_user.usage:
        billing_user.usage.storage_used_mb = round(storage_used_mb + file_size_mb, 2)

    # 先提交 Asset/Job，再派发 Worker，避免 Worker 抢先读取到不存在的记录。
    await db.commit()

    # 派发 Celery 媒体处理任务
    from app.tasks.media_tasks import process_asset
    try:
        task = process_asset.delay(asset.id, job.id)
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        asset.status = "处理失败"
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"素材已上传，但处理任务派发失败：{str(exc)[:160]}"
        job.result = None
        job.result_detail = "请在任务中心恢复 Worker 后重试该素材处理任务"
        await db.commit()

    return UploadResponse(
        asset_id=asset.id,
        name=asset.name,
        status=asset.status,
        job_id=job.id,
    )


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取素材详情。"""
    result = await db.execute(
        select(Asset)
        .join(Project)
        .where(Asset.id == asset_id, accessible_project_condition(user.id))
        .options(selectinload(Asset.clips))
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _asset_out(asset)


@router.get("/{asset_id}/clips", response_model=list[ClipOut])
async def list_asset_clips(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取素材的片段列表。"""
    result = await db.execute(
        select(Asset).join(Project).where(Asset.id == asset_id, accessible_project_condition(user.id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="素材不存在")

    clips_result = await db.execute(
        select(Clip).where(Clip.asset_id == asset_id).order_by(Clip.start_time)
    )
    return [_clip_out(c) for c in clips_result.scalars().all()]


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """仅在素材不再被脚本、时间线、素材箱或任务引用时删除。"""
    result = await db.execute(
        select(Asset).join(Project).where(Asset.id == asset_id, accessible_project_condition(user.id))
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    await require_project_access(asset.project_id, user, db, "editor")

    from app.services.deletion import asset_delete_impact

    impact = await asset_delete_impact(db, asset)
    if not impact["can_delete"]:
        raise HTTPException(status_code=409, detail="；".join(impact["blockers"]))

    clip_thumbnail_paths = list(
        (
            await db.execute(
                select(Clip.thumbnail_path).where(
                    Clip.asset_id == asset.id,
                    Clip.thumbnail_path.is_not(None),
                )
            )
        ).scalars().all()
    )
    project = await db.get(Project, asset.project_id)

    object_paths = set(
        clip_thumbnail_paths
        + ([asset.thumbnail_path] if asset.thumbnail_path else [])
        + ([asset.file_path] if asset.file_path else [])
        + ([asset.preview_path] if asset.preview_path else [])
    )

    await db.delete(asset)
    if project:
        project.asset_count = max(0, (project.asset_count or 0) - 1)
        project.clip_count = (
            await db.execute(
                select(func.count())
                .select_from(Clip)
                .join(Asset)
                .where(
                    Asset.project_id == project.id,
                    Asset.id != asset.id,
                    Clip.embedding.is_not(None),
                    Clip.embedding_model == settings.active_embedding_model,
                    Clip.embedding_dimensions == settings.ai_embedding_dimensions,
                    Clip.embedding_status == "ready",
                )
            )
        ).scalar() or 0
        remaining_assets = (
            await db.execute(
                select(func.count())
                .select_from(Asset)
                .where(Asset.project_id == project.id, Asset.id != asset.id)
            )
        ).scalar() or 0
        remaining_scripts = (
            await db.execute(
                select(func.count()).select_from(Script).where(Script.project_id == project.id)
            )
        ).scalar() or 0
        project.script_count = remaining_scripts
        if remaining_assets == 0:
            project.status = "脚本编辑中" if remaining_scripts > 0 else "等待上传"
    billing_user = (
        await db.execute(
            select(User)
            .where(User.id == project.owner_id)
            .options(selectinload(User.usage))
        )
    ).scalar_one_or_none()
    if billing_user and billing_user.usage:
        remaining_storage_mb = (
            await db.execute(
                select(func.coalesce(func.sum(Asset.file_size_mb), 0.0))
                .join(Project)
                .where(
                    Project.owner_id == project.owner_id,
                    Asset.id != asset.id,
                )
            )
        ).scalar() or 0.0
        billing_user.usage.storage_used_mb = round(remaining_storage_mb, 2)

    await db.commit()
    from app.utils.storage import delete_file

    for object_path in object_paths:
        delete_file(object_path)


@router.get("/{asset_id}/delete-impact")
async def get_asset_delete_impact(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).join(Project).where(
            Asset.id == asset_id, accessible_project_condition(user.id)
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    await require_project_access(asset.project_id, user, db, "editor")
    from app.services.deletion import asset_delete_impact

    return await asset_delete_impact(db, asset)
