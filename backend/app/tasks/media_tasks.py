"""素材处理 Celery 任务。

Pipeline: 转码 → ASR(语音转写) → OCR(画面文字识别) → 镜头切分 → 语义索引
"""

import subprocess
import json
import os
import re
import hashlib
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.tasks.celery_app import celery_app
from app.tasks.async_runner import run_async
from app.config import get_settings

settings = get_settings()


async def _update_job(job_id: str, **kwargs):
    """更新任务状态。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import update

    values = dict(kwargs)
    if "updated_at" not in values:
        values["updated_at"] = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        await session.execute(update(Job).where(Job.id == job_id).values(**values))
        await session.commit()


async def _get_job_project_owner(job_id: str) -> Optional[str]:
    """获取任务对应项目的 owner_id。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from app.models.project import Project
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project.owner_id)
            .join(Job, Job.project_id == Project.id)
            .where(Job.id == job_id)
        )
        row = result.first()
        return row[0] if row else None


async def _broadcast_ws(user_id: str, job_data: dict):
    """通过 Redis pub/sub 广播 WebSocket 消息（Celery worker 无法直接访问 FastAPI 内存）。"""
    if not user_id:
        return
    import redis.asyncio as aioredis
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.publish(
            f"ws:job_updates:{user_id}",
            json.dumps(job_data, ensure_ascii=False),
        )
    finally:
        await redis.aclose()


# ────────────────────────────────────────────
# MinIO 文件操作辅助函数
# ────────────────────────────────────────────

def _download_from_minio(object_name: str, local_path: str) -> str:
    """从 MinIO 下载文件到本地路径。"""
    from app.utils.storage import get_minio_client

    client = get_minio_client()
    obj = client.get_object(settings.minio_bucket, object_name)
    try:
        with open(local_path, "wb") as f:
            for chunk in obj.stream(amt=8192):
                f.write(chunk)
    finally:
        obj.close()
        obj.release_conn()
    return local_path


# ────────────────────────────────────────────
# FFmpeg / FFprobe 辅助函数
# ────────────────────────────────────────────

def _probe_video(file_path: str) -> dict:
    """用 ffprobe 获取视频或音频元数据。

    返回时长、画面参数以及音频编码、采样率、声道和码率。
    """
    cmd = [
        settings.ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 执行失败: {result.stderr}")

    data = json.loads(result.stdout)

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0) or 0)

    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    info = {
        "duration": duration,
        "resolution": "0x0",
        "fps": 25.0,
        "codec": "unknown",
        "has_video": video_stream is not None,
        "has_audio": audio_stream is not None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "sample_rate": (int(audio_stream.get("sample_rate") or 0) or None) if audio_stream else None,
        "channels": (int(audio_stream.get("channels") or 0) or None) if audio_stream else None,
        "bitrate": (int(audio_stream.get("bit_rate") or 0) or None) if audio_stream else None,
    }

    if video_stream:
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        info["resolution"] = f"{width}x{height}"
        info["codec"] = video_stream.get("codec_name", "unknown")
        # 解析帧率，格式如 "25/1" 或 "30000/1001"
        fps_str = video_stream.get("r_frame_rate", "25/1")
        try:
            num, den = fps_str.split("/")
            den_f = float(den)
            info["fps"] = round(float(num) / den_f, 2) if den_f != 0 else 25.0
        except (ValueError, ZeroDivisionError):
            info["fps"] = 25.0

    return info


def _normalize_audio(file_path: str, output_path: str) -> str:
    """生成浏览器兼容的 AAC/M4A 试听文件。"""
    cmd = [
        settings.ffmpeg_path,
        "-i", file_path,
        "-vn",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"音频标准化失败: {result.stderr[:240]}")
    return output_path


def _extract_keyframes(file_path: str, output_dir: str, interval: int = 10) -> list[str]:
    """用 ffmpeg 从视频中提取关键帧（每 interval 秒一帧）。

    返回帧文件路径列表（按时间排序）。
    """
    pattern = os.path.join(output_dir, "frame_%04d.jpg")
    cmd = [
        settings.ffmpeg_path,
        "-i", file_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        "-y",
        pattern,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    frames = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    return frames


def _extract_thumbnail(file_path: str, timestamp: float, output_path: str) -> str:
    """提取指定时间点的真实视频帧，供素材卡片和片段预览使用。"""
    cmd = [
        settings.ffmpeg_path,
        "-ss", str(max(0, timestamp)),
        "-i", file_path,
        "-frames:v", "1",
        "-vf", "scale=640:-2",
        "-q:v", "3",
        "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"缩略图提取失败: {result.stderr[:200]}")
    return output_path


def _extract_audio(file_path: str, output_path: str) -> str:
    """为本地 ASR 提取 16kHz 单声道 PCM WAV。"""
    cmd = [
        settings.ffmpeg_path,
        "-i", file_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"音频提取失败: {result.stderr[:200]}")
    return output_path


def _detect_scenes(file_path: str, duration: float) -> list[tuple[float, float]]:
    """用 ffmpeg 的 select=gt(scene\\,0.3) 滤镜检测场景变化点。

    返回每个场景的 (start_time, end_time) 列表。
    如果没有检测到场景变化，按固定 30 秒切分。
    """
    cmd = [
        settings.ffmpeg_path,
        "-i", file_path,
        "-vf", r"select=gt(scene\,0.3),showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    # showinfo 输出到 stderr，解析 pts_time 获取场景变化时间点
    timestamps = []
    for match in re.finditer(r"pts_time:(\d+\.?\d*)", result.stderr):
        timestamps.append(float(match.group(1)))

    # 去重并排序
    timestamps = sorted(set(timestamps))

    # 构建场景列表：[0, scene1, scene2, ..., duration]
    boundaries = [0.0] + timestamps + [duration]
    scenes = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        # 过滤过短片段（< 1 秒）
        if end - start >= 1.0:
            scenes.append((start, end))

    if not scenes:
        # 没有检测到场景变化，按固定 30 秒切分
        chunk = 30.0
        t = 0.0
        while t < duration:
            scenes.append((t, min(t + chunk, duration)))
            t += chunk

    return scenes


# ────────────────────────────────────────────
# Celery 任务定义
# ────────────────────────────────────────────

@celery_app.task(bind=True, name="app.tasks.process_asset")
def process_asset(self, asset_id: str, job_id: str):
    """素材处理完整 pipeline。"""
    run_async(_process_asset_async(asset_id, job_id))


async def _process_asset_async(asset_id: str, job_id: str):
    """异步处理素材。"""
    from app.database import async_session_factory
    from app.models.asset import Asset, Clip
    from app.models.job import Job
    from app.models.project import Project
    from app.services.ai_provider import (
        generate_embedding,
        get_active_embedding_model,
        transcribe_audio,
        recognize_text_ocr,
    )
    from app.utils.storage import delete_file, get_file_url, upload_file
    from sqlalchemy import delete, select, update, func

    owner_id = await _get_job_project_owner(job_id)

    tmp_dir = tempfile.mkdtemp(prefix="openvma_asset_")
    local_video_path = ""
    clip_count = 0

    try:
        async with async_session_factory() as session:
            # 获取素材
            result = await session.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                await _update_job(job_id, status="FAILED", detail="素材不存在")
                return

            # 重试前清理上一次不完整或错误生成的片段，避免重复计数和脏数据。
            existing_clip_count = (
                await session.execute(
                    select(func.count()).select_from(Clip).where(Clip.asset_id == asset_id)
                )
            ).scalar() or 0
            if existing_clip_count:
                project = await session.get(Project, asset.project_id)
                if project:
                    project.clip_count = max(0, (project.clip_count or 0) - existing_clip_count)
                await session.execute(delete(Clip).where(Clip.asset_id == asset_id))
            asset.status = "处理中"
            asset.thumbnail_path = None
            await session.commit()

            await _update_job(
                job_id,
                status="RUNNING",
                stage="准备处理",
                stage_index=0,
                progress=1,
                detail=f"正在准备处理 {asset.name}",
                result=None,
                result_detail="",
                result_url=None,
            )

            is_audio_asset = asset.media_type == "audio"
            stages = (
                ["音频标准化", "提取音频信息", "完成"]
                if is_audio_asset
                else ["转码", "语音转写(ASR)", "画面文字识别(OCR)", "镜头切分", "语义索引"]
            )
            file_path = asset.file_path or ""

            if not file_path:
                asset.status = "处理失败"
                await session.commit()
                await _update_job(
                    job_id,
                    status="FAILED",
                    stage="文件读取失败",
                    detail="素材文件路径为空",
                    result=None,
                    result_detail="素材记录没有关联可读取的媒体文件",
                    result_url=None,
                )
                await _broadcast_ws(owner_id, {"job_id": job_id, "status": "FAILED", "progress": 0})
                return

            # ── Stage 0: 转码 / 提取元数据 ──
            await _update_job(
                job_id, stage=stages[0], stage_index=0, progress=10,
                detail=f"正在提取元数据 {asset.name}",
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "RUNNING", "progress": 10, "stage": stages[0],
            })

            # 从 MinIO 下载文件到临时目录
            local_video_path = os.path.join(tmp_dir, os.path.basename(file_path) or "source.mp4")
            try:
                _download_from_minio(file_path, local_video_path)
            except Exception as e:
                asset.status = "处理失败"
                await session.commit()
                await _update_job(
                    job_id,
                    status="FAILED",
                    stage="文件读取失败",
                    detail=f"文件下载失败: {e}",
                    result=None,
                    result_detail="无法从对象存储读取素材文件",
                    result_url=None,
                )
                await _broadcast_ws(owner_id, {"job_id": job_id, "status": "FAILED", "progress": 10})
                return

            # 用 ffprobe 提取元数据
            try:
                probe_info = _probe_video(local_video_path)
                if probe_info["duration"] <= 0:
                    raise RuntimeError("未检测到有效媒体时长")
                if is_audio_asset and not probe_info["has_audio"]:
                    raise RuntimeError("未检测到有效音频流")
                if not is_audio_asset and not probe_info["has_video"]:
                    raise RuntimeError("未检测到有效视频流")
                asset.duration = probe_info["duration"]
                asset.resolution = probe_info["resolution"]
                asset.fps = probe_info["fps"]
                asset.codec = probe_info["codec"]
                asset.has_audio = probe_info["has_audio"]
                asset.audio_codec = probe_info["audio_codec"]
                asset.sample_rate = probe_info["sample_rate"]
                asset.channels = probe_info["channels"]
                asset.bitrate = probe_info["bitrate"]
            except Exception as e:
                asset.status = "处理失败"
                await session.commit()
                await _update_job(
                    job_id,
                    status="FAILED",
                    stage="转码失败",
                    detail=f"视频文件无法解析：{str(e)[:200]}",
                    result=None,
                    result_detail=f"{asset.name} 不是可解码的视频文件或媒体工具不可用",
                    result_url=None,
                )
                if owner_id:
                    await _broadcast_ws(owner_id, {
                        "job_id": job_id, "status": "FAILED", "progress": 10, "stage": "转码失败",
                    })
                return
            await session.commit()

            if is_audio_asset:
                await _update_job(
                    job_id,
                    stage=stages[0],
                    stage_index=0,
                    progress=45,
                    detail=f"正在生成兼容试听文件 {asset.name}",
                )
                preview_file = os.path.join(tmp_dir, "preview.m4a")
                try:
                    _normalize_audio(local_video_path, preview_file)
                    preview_path = f"audio-previews/{asset_id}/preview.m4a"
                    with open(preview_file, "rb") as preview_stream:
                        upload_file(preview_path, preview_stream.read(), "audio/mp4")
                    asset.preview_path = preview_path
                except Exception as exc:
                    asset.status = "处理失败"
                    await session.commit()
                    await _update_job(
                        job_id,
                        status="FAILED",
                        stage="音频标准化失败",
                        progress=45,
                        detail=f"音频处理失败：{str(exc)[:200]}",
                        result=None,
                        result_detail="请确认音频编码完整后重试",
                    )
                    return

                asset.status = "处理完成"
                project = await session.get(Project, asset.project_id)
                if project and project.status in {"等待上传", "处理中"}:
                    project.status = "素材已就绪"
                await session.commit()
                await _update_job(
                    job_id,
                    stage="完成",
                    stage_index=2,
                    progress=100,
                    status="SUCCEEDED",
                    detail="音频素材处理完成",
                    result="已进入素材库",
                    result_detail=(
                        f"{asset.name} 已完成标准化：{asset.audio_codec or '音频'}，"
                        f"{asset.sample_rate or 0}Hz，{asset.channels or 0} 声道"
                    ),
                )
                await _broadcast_ws(owner_id, {
                    "job_id": job_id,
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "stage": "完成",
                })
                return

            # ── Stage 1: ASR 语音转写 ──
            await _update_job(
                job_id, stage=stages[1], stage_index=1, progress=30,
                detail="正在语音转写",
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "RUNNING", "progress": 30, "stage": stages[1],
            })

            try:
                if settings.ai_asr_provider.lower() == "local":
                    local_audio_path = os.path.join(tmp_dir, "asr_audio.wav")
                    _extract_audio(local_video_path, local_audio_path)
                    transcript = await transcribe_audio(local_path=local_audio_path)
                else:
                    # 在线 ASR 需要第三方能够访问的签名 URL。
                    audio_url = get_file_url(file_path, expires_hours=2)
                    transcript = await transcribe_audio(audio_url=audio_url)
                asset.transcript = transcript
            except Exception:
                # ASR 失败，降级为空字符串
                asset.transcript = ""
            await session.commit()

            # ── Stage 2: OCR 画面文字识别 ──
            await _update_job(
                job_id, stage=stages[2], stage_index=2, progress=50,
                detail="正在识别画面文字",
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "RUNNING", "progress": 50, "stage": stages[2],
            })

            ocr_texts: list[str] = []
            ocr_observations: list[tuple[float, str]] = []
            try:
                frames_dir = os.path.join(tmp_dir, "frames")
                os.makedirs(frames_dir, exist_ok=True)
                # 每 10 秒提取一帧
                frames = _extract_keyframes(local_video_path, frames_dir, interval=10)
                for frame_index, frame_path in enumerate(frames):
                    try:
                        if settings.ai_ocr_provider.lower() == "local":
                            text = await recognize_text_ocr(local_path=frame_path)
                        else:
                            frame_object_name = f"ocr-frames/{asset_id}/{uuid.uuid4().hex[:8]}.jpg"
                            with open(frame_path, "rb") as frame_file:
                                upload_file(frame_object_name, frame_file.read(), "image/jpeg")
                            try:
                                frame_url = get_file_url(frame_object_name, expires_hours=2)
                                text = await recognize_text_ocr(image_url=frame_url)
                            finally:
                                delete_file(frame_object_name)
                        if text and text.strip():
                            normalized_text = text.strip()
                            ocr_texts.append(normalized_text)
                            ocr_observations.append((float(frame_index * 10), normalized_text))
                    except Exception:
                        continue

                asset.ocr_text = "\n".join(dict.fromkeys(ocr_texts)) if ocr_texts else ""

                # 从 OCR 文本中提取简单标签
                if ocr_texts:
                    all_ocr = " ".join(ocr_texts)
                    words = [
                        w for w in re.split(r"[\s,，。、！？：:;；]+", all_ocr)
                        if len(w) >= 2
                    ][:10]
                    asset.tags = words
            except Exception:
                asset.ocr_text = asset.ocr_text or ""
            await session.commit()

            # ── Stage 3: 镜头切分 ──
            await _update_job(
                job_id, stage=stages[3], stage_index=3, progress=70,
                detail="正在切分镜头",
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "RUNNING", "progress": 70, "stage": stages[3],
            })

            try:
                scenes = _detect_scenes(local_video_path, asset.duration)
            except Exception:
                # 降级：按 30 秒切分
                scenes = []
                t = 0.0
                while t < asset.duration:
                    scenes.append((t, min(t + 30.0, asset.duration)))
                    t += 30.0

            if not scenes:
                raise RuntimeError("没有检测到可用的视频片段")

            # 为每个场景构建片段数据
            clip_data_list = []
            for idx, (start, end) in enumerate(scenes):
                # 按时间比例截取该片段对应的转写文本
                transcript_seg = ""
                if asset.transcript and asset.duration > 0:
                    total = asset.duration
                    ratio_start = int(start / total * len(asset.transcript))
                    ratio_end = int(end / total * len(asset.transcript))
                    transcript_seg = asset.transcript[ratio_start:ratio_end].strip()

                ocr_segment = "\n".join(
                    dict.fromkeys(
                        text_value
                        for timestamp, text_value in ocr_observations
                        if start <= timestamp < end
                    )
                )

                thumbnail_path = None
                try:
                    local_thumbnail = os.path.join(tmp_dir, f"thumbnail_{idx:04d}.jpg")
                    _extract_thumbnail(local_video_path, start, local_thumbnail)
                    thumbnail_path = f"thumbnails/{asset_id}/{idx:04d}.jpg"
                    with open(local_thumbnail, "rb") as thumbnail_file:
                        upload_file(thumbnail_path, thumbnail_file.read(), "image/jpeg")
                    if idx == 0:
                        asset.thumbnail_path = thumbnail_path
                except Exception:
                    thumbnail_path = None

                clip_data_list.append({
                    "start": start,
                    "end": end,
                    "title": f"片段 {idx + 1}",
                    "transcript": transcript_seg,
                    "ocr": ocr_segment,
                    "scene_type": None,
                    "shot_type": None,
                    "camera_motion": None,
                    "persons": [],
                    "objects": [],
                    "thumbnail_path": thumbnail_path,
                })

            # ── Stage 4: 语义索引 ──
            await _update_job(
                job_id, stage=stages[4], stage_index=4, progress=90,
                detail="正在生成语义索引",
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "RUNNING", "progress": 90, "stage": stages[4],
            })

            indexed_clip_count = 0
            prepared_clips = []
            embedding_model = get_active_embedding_model()
            for clip_data in clip_data_list:
                # 为每个片段生成 embedding
                embedding_text = " ".join(
                    value.strip()
                    for value in [
                        clip_data["transcript"],
                        clip_data["ocr"],
                        " ".join(str(tag) for tag in (asset.tags or [])),
                    ]
                    if value and value.strip()
                )
                embedding = None
                embedding_status = "missing"
                if embedding_text:
                    try:
                        embedding = await generate_embedding(embedding_text)
                        embedding_status = "ready"
                    except Exception:
                        embedding = None
                        embedding_status = "failed"
                if embedding is not None:
                    indexed_clip_count += 1

                clip = Clip(
                    id=f"clip-{uuid.uuid4().hex[:12]}",
                    asset_id=asset_id,
                    start_time=clip_data["start"],
                    end_time=clip_data["end"],
                    duration=clip_data["end"] - clip_data["start"],
                    title=clip_data["title"],
                    transcript_segment=clip_data["transcript"],
                    ocr_segment=clip_data["ocr"],
                    scene_type=clip_data["scene_type"],
                    shot_type=clip_data["shot_type"],
                    camera_motion=clip_data["camera_motion"],
                    persons=clip_data["persons"],
                    objects=clip_data["objects"],
                    thumbnail_path=clip_data["thumbnail_path"],
                    embedding=embedding,
                    embedding_model=embedding_model if embedding is not None else None,
                    embedding_dimensions=settings.ai_embedding_dimensions if embedding is not None else None,
                    embedding_version=1,
                    embedding_status=embedding_status,
                    embedding_source_hash=(
                        hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
                        if embedding_text
                        else None
                    ),
                    embedding_updated_at=(datetime.now(timezone.utc) if embedding is not None else None),
                    variant=asset.variant,
                    quality_score=0.0,
                )
                prepared_clips.append(clip)

            # 基础媒体处理不应依赖 AI 服务。即使没有转写、OCR 或 Embedding，
            # 真实检测到的镜头和缩略图仍可用于人工剪辑；只是不能宣称可语义搜索。
            session.add_all(prepared_clips)

            await session.commit()
            clip_count = len(clip_data_list)

            # 更新素材状态
            asset.status = "处理完成"
            await session.commit()

            # 更新项目状态和片段数
            proj_result = await session.execute(
                select(Project).where(Project.id == asset.project_id)
            )
            project = proj_result.scalar_one_or_none()
            if project:
                total_clip_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(Clip)
                        .join(Asset)
                        .where(Asset.project_id == project.id)
                    )
                ).scalar() or 0
                searchable_clip_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(Clip)
                        .join(Asset)
                        .where(
                            Asset.project_id == project.id,
                            Clip.embedding.is_not(None),
                            Clip.embedding_model == embedding_model,
                            Clip.embedding_dimensions == settings.ai_embedding_dimensions,
                            Clip.embedding_status == "ready",
                        )
                    )
                ).scalar() or 0
                project.clip_count = searchable_clip_count
                if total_clip_count > 0 and searchable_clip_count == total_clip_count:
                    project.status = "全部可搜索"
                elif total_clip_count > 0:
                    project.status = "素材已就绪"
                await session.commit()

            if indexed_clip_count > 0:
                completion_detail = (
                    f"{asset.name} 处理完成，切分 {clip_count} 个真实片段，"
                    f"其中 {indexed_clip_count} 个已建立语义索引"
                )
                completion_message = "素材处理完成，可搜索片段已生成"
            else:
                completion_detail = (
                    f"{asset.name} 基础处理完成，切分 {clip_count} 个真实片段；"
                    "当前没有可用转写/OCR 或语义索引服务，片段可用于人工剪辑，但暂不可语义搜索"
                )
                completion_message = "基础媒体处理完成，语义搜索暂不可用"

            # ── 完成 ──
            await _update_job(
                job_id,
                stage="完成",
                stage_index=4,
                progress=100,
                status="SUCCEEDED",
                detail=completion_message,
                result="已进入素材库",
                result_detail=completion_detail,
            )
            await _broadcast_ws(owner_id, {
                "job_id": job_id, "status": "SUCCEEDED", "progress": 100, "stage": "完成",
            })
    except Exception as e:
        # 任何未覆盖异常都必须落到真实失败状态，不能让 Job 永久停在 RUNNING。
        try:
            async with async_session_factory() as failure_session:
                failed_asset = await failure_session.get(Asset, asset_id)
                if failed_asset:
                    failed_asset.status = "处理失败"
                    await failure_session.commit()
        finally:
            await _update_job(
                job_id,
                status="FAILED",
                stage="处理失败",
                detail=f"素材处理失败：{str(e)[:200]}",
                result=None,
                result_detail=str(e)[:200],
                result_url=None,
            )
            if owner_id:
                await _broadcast_ws(owner_id, {
                    "job_id": job_id, "status": "FAILED", "progress": 0, "stage": "处理失败",
                })
    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)


@celery_app.task(bind=True, name="app.tasks.retry_asset_processing")
def retry_asset_processing(self, job_id: str):
    """重试素材处理任务。"""
    try:
        run_async(_retry_asset_processing_async(job_id))
    except Exception as e:
        run_async(_update_job(
            job_id,
            status="FAILED",
            stage="重试失败",
            detail=f"素材任务重试失败：{str(e)[:200]}",
            result=None,
            result_detail=str(e)[:200],
            result_url=None,
        ))
        raise


async def _retry_asset_processing_async(job_id: str):
    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        # 查找关联的 asset
        from app.models.asset import Asset
        asset_result = await session.execute(
            select(Asset).where(
                Asset.project_id == job.project_id,
                Asset.name.contains(job.name.replace("素材处理：", "")),
            )
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            await _process_asset_async(asset.id, job_id)
