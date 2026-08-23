"""用户级全局素材库：游标分页、上传、图片支持、片段与引用分析。"""

import asyncio
import base64
import io
import json
import math
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import Text, and_, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, AssetSegment, ProjectAssetLink
from app.models.job import Job
from app.models.project import Project, ProjectComposition
from app.models.script import Shot
from app.models.user import User
from app.schemas.asset import (
    AssetCursorListOut,
    AssetDeleteImpactOut,
    AssetOut,
    AssetSegmentOut,
    UploadResponse,
)
from app.services.project_access import require_project_access
from app.services.quotas import QuotaExceededError, admit_job_quota
from app.services.storage_usage import recalculate_storage_usage
from app.utils.storage import delete_file, get_file_url, upload_stream


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
_IMAGE_FORMATS = {
    "JPEG": ({".jpg", ".jpeg"}, "image/jpeg"),
    "PNG": ({".png"}, "image/png"),
    "WEBP": ({".webp"}, "image/webp"),
    "GIF": ({".gif"}, "image/gif"),
}

_AI_SOURCE_TYPES = {
    "ai",
    "ai_generated",
    "ai-generated",
    "generated",
    "imagegen",
    "text_to_image",
    "text_to_video",
}
_CONTENT_TYPE_KEYS = {
    "scene": {"space", "spaces", "scene", "scenes", "place", "places", "location", "locations"},
    "role": {"person", "people", "persons", "character", "characters", "role", "roles", "speaker", "speakers"},
    "object": {"object", "objects", "item", "items", "product", "products"},
    "event": {"action", "actions", "event", "events", "activity", "activities"},
}


def _has_recognition_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_recognition_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_recognition_value(item) for item in value)
    return value is not None and value is not False and str(value).strip() != ""


def _asset_content_types(asset: Asset, *, include_segments: bool = True) -> list[str]:
    result: set[str] = set()
    recognitions = [asset.recognition or {}]
    if include_segments:
        recognitions.extend((segment.recognition or {}) for segment in getattr(asset, "segments", []) or [])
    for recognition in recognitions:
        normalized = {str(key).strip().lower(): value for key, value in recognition.items()}
        for content_type, keys in _CONTENT_TYPE_KEYS.items():
            if any(_has_recognition_value(normalized.get(key)) for key in keys):
                result.add(content_type)

    explicit_text = " ".join(str(tag) for tag in (asset.tags or [])).lower()
    aliases = {
        "scene": ("场景", "空间", "scene", "space", "place", "location"),
        "role": ("角色", "人物", "说话人", "role", "person", "people", "character", "speaker"),
        "object": ("物品", "物体", "产品", "object", "item", "product"),
        "event": ("事件", "动作", "活动", "event", "action", "activity"),
    }
    for content_type, words in aliases.items():
        if any(word in explicit_text for word in words):
            result.add(content_type)
    return [item for item in ("scene", "role", "object", "event") if item in result]


def _asset_source_category(asset: Asset) -> str:
    normalized = (asset.source_type or "").strip().lower()
    return "ai" if normalized in _AI_SOURCE_TYPES or normalized.startswith("ai_") else "non-ai"


def _safe_filename(filename: str | None) -> str:
    basename = Path(filename or "未命名素材").name.strip()
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", basename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
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
    current = upload.file.tell()
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(current)
    return size


def _validate_upload_size(file_size: int, max_size_gb: int | None = None) -> None:
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    size_limit_gb = settings.max_upload_size_gb if max_size_gb is None else max_size_gb
    if file_size > size_limit_gb * 1024 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"单个文件不能超过 {size_limit_gb} GiB")


def _probe_upload_stream(upload: UploadFile) -> dict:
    stream = upload.file
    stream.seek(0)
    descriptor = stream.fileno()
    result = subprocess.run(
        [
            settings.ffprobe_path,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            f"/dev/fd/{descriptor}",
        ],
        pass_fds=(descriptor,),
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
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
    has_video = bool(video_stream)
    has_audio = bool(audio_stream)
    if not has_video and not has_audio:
        raise HTTPException(status_code=415, detail="文件中没有可用的视频轨或音频轨")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise HTTPException(status_code=415, detail="媒体时长无效或文件尚未完整写入")
    data["openvma"] = {
        "media_type": "video" if has_video else "audio",
        "has_audio": has_audio,
        "duration_ms": max(1, round(duration * 1000)),
        "width": int(video_stream.get("width") or 0) or None,
        "height": int(video_stream.get("height") or 0) or None,
        "codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "sample_rate": int(audio_stream.get("sample_rate") or 0) or None,
        "channels": int(audio_stream.get("channels") or 0) or None,
        "bitrate": int(audio_stream.get("bit_rate") or 0) or None,
    }
    return data


def _probe_image(upload: UploadFile) -> dict | None:
    stream = upload.file
    stream.seek(0)
    try:
        image = Image.open(stream)
        image_format = str(image.format or "").upper()
        width, height = image.size
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        stream.seek(0)
        return None
    finally:
        stream.seek(0)
    if image_format not in _IMAGE_FORMATS:
        return None
    return {
        "format": image_format,
        "width": width,
        "height": height,
        "mime_type": _IMAGE_FORMATS[image_format][1],
    }


def _encode_cursor(asset: Asset) -> str:
    payload = json.dumps(
        {"created_at": asset.created_at.isoformat(), "id": asset.id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return datetime.fromisoformat(payload["created_at"]), str(payload["id"])
    except Exception as exc:
        raise HTTPException(status_code=422, detail="素材游标无效") from exc


def _segment_out(segment: AssetSegment) -> AssetSegmentOut:
    return AssetSegmentOut.model_validate(segment).model_copy(
        update={
            "duration_ms": segment.duration_ms,
            "thumbnail_url": get_file_url(segment.thumbnail_path) if segment.thumbnail_path else None,
        }
    )


def _match_excerpt(value: str | None, needle: str, context: int = 36) -> str | None:
    text_value = (value or "").strip()
    if not text_value:
        return None
    index = text_value.casefold().find(needle.casefold())
    if index < 0:
        return None
    start = max(0, index - context)
    end = min(len(text_value), index + len(needle) + context)
    return f"{'…' if start else ''}{text_value[start:end].strip()}{'…' if end < len(text_value) else ''}"


def asset_out(
    asset: Asset,
    search: str = "",
    *,
    include_segments: bool = True,
    classify_segments: bool | None = None,
    project_ids: list[str] | None = None,
) -> AssetOut:
    match_field = None
    match_excerpt = None
    matched_segment_id = None
    if search:
        for field, value in (
            ("name", asset.name),
            ("tag", " / ".join(str(tag) for tag in asset.tags or [])),
            ("transcript", asset.transcript),
            ("ocr", asset.ocr_text),
        ):
            excerpt = _match_excerpt(value, search)
            if excerpt:
                match_field, match_excerpt = field, excerpt
                break
        if not match_field:
            for segment in getattr(asset, "segments", []) or []:
                for field, value in (
                    ("segment_title", segment.title),
                    ("segment_transcript", segment.transcript),
                    ("segment_ocr", segment.ocr_text),
                ):
                    excerpt = _match_excerpt(value, search)
                    if excerpt:
                        match_field, match_excerpt, matched_segment_id = field, excerpt, segment.id
                        break
                if match_field:
                    break
    playable_path = asset.preview_path or asset.file_path
    # 显式构造，避免 Pydantic 在 include_segments=False 时仍访问 SQLAlchemy
    # 的 lazy relationship，从而在异步请求中触发 MissingGreenlet。
    return AssetOut(
        id=asset.id,
        owner_id=asset.owner_id,
        name=asset.name,
        media_type=asset.media_type,
        source_type=asset.source_type,
        source_category=_asset_source_category(asset),
        content_types=_asset_content_types(
            asset,
            include_segments=include_segments if classify_segments is None else classify_segments,
        ),
        status=asset.status,
        processing_status=asset.processing_status,
        mime_type=asset.mime_type,
        duration_ms=asset.duration_ms,
        width=asset.width,
        height=asset.height,
        has_audio=asset.has_audio,
        file_size_mb=asset.file_size_mb,
        tags=asset.tags or [],
        recognition=asset.recognition or {},
        asset_metadata=getattr(asset, "asset_metadata", None) or {},
        media_url=get_file_url(playable_path) if playable_path else None,
        thumbnail_url=get_file_url(asset.thumbnail_path) if asset.thumbnail_path else None,
        match_field=match_field,
        match_excerpt=match_excerpt,
        matched_segment_id=matched_segment_id,
        project_ids=project_ids or [],
        segments=(
            [_segment_out(item) for item in (getattr(asset, "segments", []) or [])]
            if include_segments
            else []
        ),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.get("", response_model=AssetCursorListOut)
async def list_assets(
    project_id: str = Query(""),
    media_type: str = Query(""),
    source_type: str = Query(""),
    source_category: str = Query(""),
    search: str = Query(""),
    status_filter: str = Query("", alias="status"),
    cursor: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Asset).where(Asset.owner_id == user.id, Asset.deleted_at.is_(None))
    if project_id:
        await require_project_access(project_id, user, db)
        query = query.join(ProjectAssetLink).where(ProjectAssetLink.project_id == project_id)
    if media_type:
        if media_type not in {"image", "video", "audio"}:
            raise HTTPException(status_code=422, detail="媒体类型仅支持 image、video 或 audio")
        query = query.where(Asset.media_type == media_type)
    if source_type:
        query = query.where(Asset.source_type == source_type)
    if source_category:
        if source_category not in {"ai", "non-ai"}:
            raise HTTPException(status_code=422, detail="来源分类仅支持 ai 或 non-ai")
        normalized_source = func.lower(Asset.source_type)
        ai_condition = or_(
            normalized_source.in_(_AI_SOURCE_TYPES),
            normalized_source.like("ai\\_%", escape="\\"),
        )
        query = query.where(ai_condition if source_category == "ai" else ~ai_condition)
    if status_filter:
        query = query.where(Asset.status == status_filter)
    if search:
        keyword = f"%{search.strip()}%"
        segment_match = exists(
            select(1).where(
                AssetSegment.asset_id == Asset.id,
                or_(
                    AssetSegment.title.ilike(keyword),
                    AssetSegment.transcript.ilike(keyword),
                    AssetSegment.ocr_text.ilike(keyword),
                ),
            )
        )
        query = query.where(
            or_(
                Asset.name.ilike(keyword),
                Asset.transcript.ilike(keyword),
                Asset.ocr_text.ilike(keyword),
                cast(Asset.tags, Text).ilike(keyword),
                segment_match,
            )
        )
    if cursor:
        created_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                Asset.created_at < created_at,
                and_(Asset.created_at == created_at, Asset.id < cursor_id),
            )
        )
    assets = (
        await db.execute(
            query.options(selectinload(Asset.segments), selectinload(Asset.project_links))
            .order_by(Asset.created_at.desc(), Asset.id.desc())
            .limit(limit + 1)
        )
    ).scalars().unique().all()
    has_more = len(assets) > limit
    items = assets[:limit]
    return AssetCursorListOut(
        items=[
            asset_out(
                item,
                search,
                include_segments=False,
                classify_segments=True,
                project_ids=sorted({link.project_id for link in item.project_links}),
            )
            for item in items
        ],
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
        has_more=has_more,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_asset(
    file: UploadFile = File(...),
    project_id: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if project_id:
        await require_project_access(project_id, user, db, "editor")
    billing_user = (
        await db.execute(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.membership), selectinload(User.usage))
        )
    ).scalar_one()
    safe_name = _safe_filename(file.filename)
    file_size = await asyncio.to_thread(_file_size, file)
    _validate_upload_size(file_size)

    image_info = await asyncio.to_thread(_probe_image, file)
    media_info: dict
    content_type: str
    if image_info:
        suffixes, expected_type = _IMAGE_FORMATS[image_info["format"]]
        if Path(safe_name).suffix.lower() not in suffixes:
            raise HTTPException(status_code=415, detail="图片扩展名与真实图片格式不一致")
        content_type = expected_type
        media_info = {
            "media_type": "image",
            "has_audio": False,
            "duration_ms": 0,
            "width": image_info["width"],
            "height": image_info["height"],
            "codec": image_info["format"].lower(),
            "audio_codec": None,
            "sample_rate": None,
            "channels": None,
            "bitrate": None,
        }
    else:
        await file.seek(0)
        header = await file.read(64)
        await file.seek(0)
        container = _detect_container(header)
        if not container:
            raise HTTPException(status_code=415, detail="仅支持真实图片、视频和常见音频文件")
        if Path(safe_name).suffix.lower() not in _CONTAINER_EXTENSIONS[container]:
            raise HTTPException(status_code=415, detail="文件扩展名与真实媒体容器不一致")
        media_info = (await asyncio.to_thread(_probe_upload_stream, file))["openvma"]
        content_type = (
            "audio/mp4"
            if media_info["media_type"] == "audio" and container == "mp4"
            else _CONTAINER_CONTENT_TYPES[container]
        )

    file_size_mb = file_size / (1024 * 1024)
    storage_used_mb = (
        await db.execute(
            select(func.coalesce(func.sum(Asset.file_size_mb), 0.0)).where(
                Asset.owner_id == user.id
            )
        )
    ).scalar() or 0.0
    storage_limit_mb = (billing_user.membership.storage_gb if billing_user.membership else 5) * 1024
    if storage_used_mb + file_size_mb > storage_limit_mb:
        raise HTTPException(status_code=413, detail="全局素材库存储空间不足")

    object_name = f"assets/{user.id}/{uuid.uuid4().hex}/{safe_name}"
    await file.seek(0)
    try:
        await asyncio.to_thread(
            upload_stream, object_name, file.file, file_size, content_type
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"对象存储写入失败：{str(exc)[:160]}") from exc
    finally:
        await file.seek(0)

    job = Job(
        owner_id=user.id,
        project_id=project_id,
        subject_type="asset",
        name=f"素材处理：{safe_name}",
        type="素材处理",
        status="QUEUED",
        stage="等待处理",
        stages=(
            ["图片解析", "OCR", "视觉理解", "语义索引", "完成"]
            if media_info["media_type"] == "image"
            else ["音频标准化", "语音转写", "语义索引", "完成"]
            if media_info["media_type"] == "audio"
            else ["媒体解析", "代理转码", "语音转写", "OCR", "镜头切分", "视觉理解", "语义索引", "完成"]
        ),
        progress=0,
        detail=f"{safe_name} 已进入处理队列",
        eta="预计 1-5 分钟",
        payload={},
    )
    processing_seconds = max(1, math.ceil(media_info["duration_ms"] / 1000))
    try:
        await admit_job_quota(db, job, user.id, "processing_seconds", processing_seconds)
    except QuotaExceededError as exc:
        await asyncio.to_thread(delete_file, object_name)
        raise HTTPException(status_code=403, detail="素材处理额度不足") from exc

    asset = Asset(
        owner_id=user.id,
        name=safe_name,
        media_type=media_info["media_type"],
        source_type="upload",
        status="processing",
        processing_status="pending",
        mime_type=content_type,
        file_path=object_name,
        file_size_mb=round(file_size_mb, 2),
        width=media_info["width"],
        height=media_info["height"],
        duration_ms=media_info["duration_ms"],
        codec=media_info["codec"],
        has_audio=media_info["has_audio"],
        audio_codec=media_info["audio_codec"],
        sample_rate=media_info["sample_rate"],
        channels=media_info["channels"],
        bitrate=media_info["bitrate"],
    )
    db.add(asset)
    await db.flush()
    job.subject_id = asset.id
    job.payload = {"asset_id": asset.id}
    db.add(job)
    if project_id:
        db.add(
            ProjectAssetLink(
                project_id=project_id,
                asset_id=asset.id,
                role="source",
                linked_by=user.id,
            )
        )
    await recalculate_storage_usage(db, user.id)
    await db.commit()

    from app.tasks.media_tasks import process_asset
    from app.services.task_dispatch import dispatch_owner_task

    try:
        task = await dispatch_owner_task(db, user.id, process_asset, asset.id, job.id)
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        asset.status = "failed"
        asset.processing_status = "failed"
        job.status = "FAILED"
        job.stage = "任务派发失败"
        job.detail = f"素材已上传，但处理任务派发失败：{str(exc)[:160]}"
        await db.commit()

    return UploadResponse(
        asset_id=asset.id,
        name=asset.name,
        media_type=asset.media_type,
        status=asset.status,
        job_id=job.id,
    )


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = (
        await db.execute(
            select(Asset)
            .where(Asset.id == asset_id, Asset.owner_id == user.id, Asset.deleted_at.is_(None))
            .options(selectinload(Asset.segments), selectinload(Asset.project_links))
        )
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    return asset_out(asset, project_ids=sorted({link.project_id for link in asset.project_links}))


@router.get("/{asset_id}/segments", response_model=list[AssetSegmentOut])
async def list_asset_segments(
    asset_id: str,
    cursor: str = Query(""),
    limit: int = Query(100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(Asset, asset_id)
    if not asset or asset.owner_id != user.id or asset.deleted_at:
        raise HTTPException(status_code=404, detail="素材不存在")
    query = select(AssetSegment).where(AssetSegment.asset_id == asset_id)
    if cursor:
        try:
            start_ms, segment_id = cursor.split(":", 1)
            query = query.where(
                or_(
                    AssetSegment.start_ms > int(start_ms),
                    and_(AssetSegment.start_ms == int(start_ms), AssetSegment.id > segment_id),
                )
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail="片段游标无效") from exc
    segments = (
        await db.execute(
            query.order_by(AssetSegment.start_ms, AssetSegment.id).limit(limit)
        )
    ).scalars().all()
    return [_segment_out(item) for item in segments]


async def _delete_impact(db: AsyncSession, asset: Asset) -> AssetDeleteImpactOut:
    project_count = (
        await db.execute(
            select(func.count(func.distinct(Project.id))).where(
                or_(
                    Project.cover_asset_id == asset.id,
                    Project.master_output_asset_id == asset.id,
                    exists(
                        select(1).where(
                            ProjectAssetLink.project_id == Project.id,
                            ProjectAssetLink.asset_id == asset.id,
                        )
                    ),
                )
            )
        )
    ).scalar() or 0
    shot_count = (
        await db.execute(
            select(func.count()).select_from(Shot).where(Shot.asset_id == asset.id)
        )
    ).scalar() or 0
    composition_count = (
        await db.execute(
            select(func.count()).select_from(ProjectComposition).where(
                ProjectComposition.current_render_asset_id == asset.id
            )
        )
    ).scalar() or 0
    blockers = []
    if project_count:
        blockers.append(f"仍被 {project_count} 个项目关联")
    if shot_count:
        blockers.append(f"仍被 {shot_count} 个镜头使用")
    if composition_count:
        blockers.append(f"仍被 {composition_count} 支主成片使用")
    return AssetDeleteImpactOut(
        can_delete=not blockers,
        project_count=int(project_count),
        shot_count=int(shot_count),
        composition_count=int(composition_count),
        blockers=blockers,
    )


@router.get("/{asset_id}/delete-impact", response_model=AssetDeleteImpactOut)
async def asset_delete_impact(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(Asset, asset_id)
    if not asset or asset.owner_id != user.id or asset.deleted_at:
        raise HTTPException(status_code=404, detail="素材不存在")
    return await _delete_impact(db, asset)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: str,
    confirmed: bool = Query(False),
    permanent: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除全局素材前必须确认")
    asset = await db.get(Asset, asset_id)
    if not asset or asset.owner_id != user.id or asset.deleted_at:
        raise HTTPException(status_code=404, detail="素材不存在")
    impact = await _delete_impact(db, asset)
    if not impact.can_delete:
        raise HTTPException(status_code=409, detail="；".join(impact.blockers))
    if not permanent:
        asset.deleted_at = datetime.now(timezone.utc)
        return

    object_paths = {
        path
        for path in (asset.file_path, asset.preview_path, asset.thumbnail_path)
        if path
    }
    object_paths.update(
        path
        for path in (
            await db.execute(
                select(AssetSegment.thumbnail_path).where(
                    AssetSegment.asset_id == asset.id,
                    AssetSegment.thumbnail_path.is_not(None),
                )
            )
        ).scalars().all()
        if path
    )
    await db.delete(asset)
    await db.flush()
    await recalculate_storage_usage(db, user.id)
    for path in object_paths:
        await asyncio.to_thread(delete_file, path)


@router.post("/{asset_id}/restore", response_model=AssetOut)
async def restore_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = (
        await db.execute(
            select(Asset)
            .where(Asset.id == asset_id, Asset.owner_id == user.id, Asset.deleted_at.is_not(None))
            .options(selectinload(Asset.segments), selectinload(Asset.project_links))
        )
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="回收站中不存在该素材")
    asset.deleted_at = None
    await db.flush()
    return asset_out(asset, project_ids=sorted({link.project_id for link in asset.project_links}))
