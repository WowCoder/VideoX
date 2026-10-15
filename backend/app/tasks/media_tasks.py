"""全局图片、视频和音频素材处理任务。"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.quotas import complete_job_success, fail_job
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


settings = get_settings()


async def _update_job(job_id: str, **kwargs) -> bool:
    from app.database import async_session_factory
    from app.models.job import Job
    from sqlalchemy import update

    values = dict(kwargs)
    values.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session_factory() as session:
        if values.get("status") == "SUCCEEDED":
            values.pop("status")
            completed = await complete_job_success(session, job_id, values=values)
        elif values.get("status") == "FAILED":
            values.pop("status")
            completed = await fail_job(session, job_id, detail=str(values.get("detail") or "任务执行失败"), stage=str(values.get("stage") or "执行失败"), error_code=values.get("error_code"), error_category=values.get("error_category"))
        else:
            statement = update(Job).where(Job.id == job_id)
            if values.get("status") in {"RUNNING", "FAILED"} or "status" not in values:
                statement = statement.where(Job.status.in_(["QUEUED", "RUNNING"]))
            result = await session.execute(statement.values(**values))
            completed = bool(result.rowcount)
        await session.commit()
        return completed


async def _get_job_owner(job_id: str) -> str | None:
    from app.database import async_session_factory
    from app.models.job import Job

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        return job.owner_id if job else None


async def _broadcast_ws(user_id: str | None, job_data: dict) -> None:
    if not user_id:
        return
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.publish(
            f"ws:job_updates:{user_id}", json.dumps(job_data, ensure_ascii=False)
        )
    finally:
        await redis.aclose()


def _download_from_minio(object_name: str, local_path: str) -> str:
    from app.utils.storage import get_minio_client

    client = get_minio_client()
    obj = client.get_object(settings.minio_bucket, object_name)
    try:
        with open(local_path, "wb") as stream:
            for chunk in obj.stream(amt=8192):
                stream.write(chunk)
    finally:
        obj.close()
        obj.release_conn()
    return local_path


def _probe_video(file_path: str) -> dict:
    result = subprocess.run(
        [
            settings.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 执行失败: {result.stderr[:240]}")
    data = json.loads(result.stdout)
    duration = float((data.get("format") or {}).get("duration") or 0)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    fps = 25.0
    if video:
        try:
            numerator, denominator = str(video.get("r_frame_rate") or "25/1").split("/")
            fps = float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            fps = 25.0
    return {
        "duration": duration,
        "width": int((video or {}).get("width") or 0) or None,
        "height": int((video or {}).get("height") or 0) or None,
        "fps": round(fps, 2),
        "codec": (video or {}).get("codec_name"),
        "has_video": bool(video),
        "has_audio": bool(audio),
        "audio_codec": (audio or {}).get("codec_name"),
        "sample_rate": int((audio or {}).get("sample_rate") or 0) or None,
        "channels": int((audio or {}).get("channels") or 0) or None,
        "bitrate": int((audio or {}).get("bit_rate") or 0) or None,
    }


def _normalize_audio(file_path: str, output_path: str) -> str:
    result = subprocess.run(
        [
            settings.ffmpeg_path,
            "-i", file_path,
            "-vn",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-movflags", "+faststart",
            "-y", output_path,
        ],
        capture_output=True,
        text=True,
        timeout=1200,
    )
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"音频标准化失败: {result.stderr[:240]}")
    return output_path


def _transcode_video_proxy(file_path: str, output_path: str) -> str:
    """Create a seek-friendly browser proxy while preserving the source for export."""
    result = subprocess.run(
        [
            settings.ffmpeg_path,
            "-i", file_path,
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-sn",
            "-dn",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-crf", "23",
            "-maxrate", "4M",
            "-bufsize", "8M",
            "-g", "30",
            "-keyint_min", "30",
            "-sc_threshold", "0",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ar", "48000",
            "-ac", "2",
            "-map_metadata", "-1",
            "-movflags", "+faststart",
            "-y", output_path,
        ],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError(f"视频代理转码失败: {result.stderr[:240]}")
    return output_path


def _extract_keyframes(file_path: str, output_dir: str, interval: int = 10) -> list[str]:
    pattern = os.path.join(output_dir, "frame_%04d.jpg")
    subprocess.run(
        [settings.ffmpeg_path, "-i", file_path, "-vf", f"fps=1/{interval}", "-q:v", "2", "-y", pattern],
        capture_output=True,
        text=True,
        timeout=600,
    )
    return sorted(
        os.path.join(output_dir, item)
        for item in os.listdir(output_dir)
        if item.startswith("frame_") and item.endswith(".jpg")
    )


def _extract_thumbnail(file_path: str, timestamp: float, output_path: str) -> str:
    result = subprocess.run(
        [
            settings.ffmpeg_path,
            "-ss", str(max(0, timestamp)),
            "-i", file_path,
            "-frames:v", "1",
            "-vf", "scale=640:-2",
            "-q:v", "3",
            "-y", output_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"缩略图提取失败: {result.stderr[:200]}")
    return output_path


def _extract_audio(file_path: str, output_path: str) -> str:
    result = subprocess.run(
        [
            settings.ffmpeg_path,
            "-i", file_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            "-y", output_path,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"音频提取失败: {result.stderr[:200]}")
    return output_path


def _detect_scenes(file_path: str, duration: float) -> list[tuple[float, float]]:
    result = subprocess.run(
        [settings.ffmpeg_path, "-i", file_path, "-vf", r"select=gt(scene\,0.3),showinfo", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    timestamps = sorted(
        {float(match.group(1)) for match in re.finditer(r"pts_time:(\d+\.?\d*)", result.stderr)}
    )
    boundaries = [0.0, *timestamps, duration]
    scenes = [
        (boundaries[index], boundaries[index + 1])
        for index in range(len(boundaries) - 1)
        if boundaries[index + 1] - boundaries[index] >= 1.0
    ]
    if not scenes:
        cursor = 0.0
        while cursor < duration:
            scenes.append((cursor, min(cursor + 30.0, duration)))
            cursor += 30.0
    return scenes


async def _embedding(text: str) -> tuple[list[float] | None, str, str | None]:
    from app.services.ai_provider import generate_embedding, get_active_embedding_model

    normalized = text.strip()
    if not normalized:
        return None, "missing", None
    try:
        value = await generate_embedding(normalized)
        return value, "ready", get_active_embedding_model()
    except Exception:
        return None, "failed", None


async def _recognize_image(local_path: str) -> str:
    from app.services.ai_provider import recognize_text_ocr
    from app.utils.storage import delete_file, get_file_url, upload_file

    if settings.ai_ocr_provider.lower() == "local":
        return await recognize_text_ocr(local_path=local_path)
    temporary_path = f"ocr-frames/{hashlib.sha256(local_path.encode()).hexdigest()[:24]}.jpg"
    with open(local_path, "rb") as stream:
        upload_file(temporary_path, stream.read(), "image/jpeg")
    try:
        return await recognize_text_ocr(
            image_url=get_file_url(temporary_path, expires_hours=2)
        )
    finally:
        delete_file(temporary_path)


def _recognition_tags(recognition: dict) -> list[str]:
    tags = [str(item).strip() for item in recognition.get("tags", []) if str(item).strip()]
    for key in ("spaces", "people", "objects", "actions"):
        for entity in recognition.get(key, []) if isinstance(recognition.get(key), list) else []:
            if isinstance(entity, dict):
                tags.extend(
                    value for value in (
                        str(entity.get("label") or "").strip(),
                        str(entity.get("role") or "").strip(),
                    ) if value
                )
    return list(dict.fromkeys(tags))[:20]


def _aggregate_recognition(recognitions: list[dict], status: str = "ready") -> dict:
    summaries = [
        summary
        for summary in dict.fromkeys(str(item.get("summary") or "").strip() for item in recognitions)
        if summary
    ]
    aggregate: dict = {
        "analysis_status": status,
        "summary": "；".join(summaries)[:2000],
        "spaces": [],
        "people": [],
        "objects": [],
        "actions": [],
        "tags": [],
    }
    for key in ("spaces", "people", "objects", "actions"):
        seen: set[tuple[str, str]] = set()
        for recognition in recognitions:
            for entity in recognition.get(key, []) if isinstance(recognition.get(key), list) else []:
                if not isinstance(entity, dict):
                    continue
                identity = (
                    str(entity.get("label") or "").strip().casefold(),
                    str(entity.get("role") or "").strip().casefold(),
                )
                if not identity[0] or identity in seen:
                    continue
                seen.add(identity)
                aggregate[key].append(entity)
        aggregate[key] = aggregate[key][:50]
    aggregate["tags"] = list(dict.fromkeys(
        tag for recognition in recognitions for tag in _recognition_tags(recognition)
    ))[:30]
    if recognitions:
        aggregate["provider"] = recognitions[0].get("provider")
        aggregate["model"] = recognitions[0].get("model")
        quality_values: dict[str, list[float]] = {
            "sharpness": [], "stability": [], "exposure": [], "usable_score": [],
        }
        for recognition in recognitions:
            quality = recognition.get("quality") if isinstance(recognition.get("quality"), dict) else {}
            for key in quality_values:
                if isinstance(quality.get(key), (int, float)):
                    quality_values[key].append(float(quality[key]))
        aggregate["quality"] = {
            key: round(sum(values) / len(values), 2)
            for key, values in quality_values.items() if values
        }
        representative = max(
            recognitions,
            key=lambda item: float((item.get("quality") or {}).get("usable_score") or 0),
        )
        if isinstance(representative.get("shot"), dict):
            aggregate["shot"] = representative["shot"]
    return aggregate


async def _visual_recognitions(items: list[dict]) -> dict[int, dict]:
    from app.services.ai_provider import analyze_visual_segments

    results: dict[int, dict] = {}
    for offset in range(0, len(items), 12):
        for recognition in await analyze_visual_segments(items[offset:offset + 12]):
            results[int(recognition["index"])] = recognition
    return results


@celery_app.task(bind=True, name="app.tasks.process_asset")
def process_asset(self, asset_id: str, job_id: str):
    run_async(_process_asset_async(asset_id, job_id))


async def _process_asset_async(asset_id: str, job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.asset import Asset, AssetSegment
    from app.services.ai_provider import transcribe_audio
    from app.utils.storage import get_file_url, upload_file, upload_stream
    from sqlalchemy import delete

    owner_id = await _get_job_owner(job_id)
    temp_dir = tempfile.mkdtemp(prefix="videox_asset_")
    try:
        async with async_session_factory() as session:
            asset = await session.get(Asset, asset_id)
            if not asset or not asset.file_path:
                await _update_job(job_id, status="FAILED", stage="素材不存在", detail="素材或文件路径不存在")
                return
            await session.execute(delete(AssetSegment).where(AssetSegment.asset_id == asset.id))
            asset.status = "processing"
            asset.processing_status = "processing"
            await session.commit()
            await _update_job(job_id, status="RUNNING", stage="准备处理", progress=5, detail=asset.name)
            await _broadcast_ws(owner_id, {"job_id": job_id, "status": "RUNNING", "progress": 5})

            local_path = os.path.join(temp_dir, Path(asset.file_path).name or "source")
            _download_from_minio(asset.file_path, local_path)

            if asset.media_type == "image":
                await _update_job(job_id, stage="图片识别", progress=30)
                with Image.open(local_path) as image:
                    asset.width, asset.height = image.size
                    thumbnail_local = os.path.join(temp_dir, "thumbnail.jpg")
                    preview = image.convert("RGB")
                    preview.thumbnail((960, 960))
                    preview.save(thumbnail_local, "JPEG", quality=86)
                thumbnail_path = f"thumbnails/{asset.id}/image.jpg"
                with open(thumbnail_local, "rb") as stream:
                    upload_file(thumbnail_path, stream.read(), "image/jpeg")
                asset.thumbnail_path = thumbnail_path
                try:
                    asset.ocr_text = (await _recognize_image(local_path)).strip()
                except Exception:
                    asset.ocr_text = ""
                await _update_job(job_id, stage="视觉理解", progress=60)
                try:
                    visual = (await _visual_recognitions([{
                        "index": 0,
                        "local_path": thumbnail_local,
                        "ocr": asset.ocr_text or "",
                    }])).get(0, {})
                    if not visual:
                        raise RuntimeError("视觉模型没有返回图片识别结果")
                    asset.recognition = _aggregate_recognition([visual])
                    asset.tags = list(dict.fromkeys([*(asset.tags or []), *_recognition_tags(visual)]))[:20]
                except Exception as exc:
                    asset.recognition = {
                        "analysis_status": "failed" if settings.has_vision else "disabled",
                        "summary": "",
                        "error": str(exc)[:300],
                    }
                    visual = asset.recognition
                embedding_text = " ".join(value for value in (
                    asset.name,
                    asset.ocr_text or "",
                    str(visual.get("summary") or ""),
                    " ".join(asset.tags or []),
                ) if value)
                embedding, embedding_status, embedding_model = await _embedding(embedding_text)
                session.add(
                    AssetSegment(
                        asset_id=asset.id,
                        start_ms=0,
                        end_ms=0,
                        title=asset.name,
                        ocr_text=asset.ocr_text or "",
                        tags=asset.tags or [],
                        recognition=visual,
                        thumbnail_path=thumbnail_path,
                        embedding=embedding,
                        embedding_model=embedding_model,
                        embedding_dimensions=settings.ai_embedding_dimensions if embedding else None,
                        embedding_status=embedding_status,
                        embedding_source_hash=hashlib.sha256(embedding_text.encode()).hexdigest(),
                        embedding_updated_at=datetime.now(timezone.utc) if embedding else None,
                        quality_score=float((visual.get("quality") or {}).get("usable_score") or min(100.0, ((asset.width or 0) * (asset.height or 0)) / 20736)),
                    )
                )

            elif asset.media_type == "audio":
                await _update_job(job_id, stage="音频标准化", progress=25)
                info = _probe_video(local_path)
                if not info["has_audio"] or info["duration"] <= 0:
                    raise RuntimeError("未检测到有效音频流")
                asset.duration_ms = round(info["duration"] * 1000)
                asset.audio_codec = info["audio_codec"]
                asset.sample_rate = info["sample_rate"]
                asset.channels = info["channels"]
                asset.bitrate = info["bitrate"]
                preview_local = os.path.join(temp_dir, "preview.m4a")
                _normalize_audio(local_path, preview_local)
                preview_path = f"audio-previews/{asset.id}/preview.m4a"
                with open(preview_local, "rb") as stream:
                    upload_file(preview_path, stream.read(), "audio/mp4")
                asset.preview_path = preview_path
                await _update_job(job_id, stage="语音转写", progress=55)
                try:
                    if settings.ai_asr_provider.lower() == "local":
                        wav_path = os.path.join(temp_dir, "asr.wav")
                        _extract_audio(local_path, wav_path)
                        asset.transcript = await transcribe_audio(local_path=wav_path)
                    else:
                        asset.transcript = await transcribe_audio(
                            audio_url=get_file_url(asset.file_path, expires_hours=2)
                        )
                except Exception:
                    asset.transcript = ""
                asset.recognition = {
                    "analysis_status": "text_only",
                    "summary": (asset.transcript or "")[:1000],
                    "spaces": [],
                    "people": [],
                    "objects": [],
                    "actions": [],
                    "tags": [],
                }
                embedding_text = " ".join(value for value in (asset.name, asset.transcript or "") if value)
                embedding, embedding_status, embedding_model = await _embedding(embedding_text)
                session.add(
                    AssetSegment(
                        asset_id=asset.id,
                        start_ms=0,
                        end_ms=asset.duration_ms,
                        title=asset.name,
                        transcript=asset.transcript or "",
                        recognition=asset.recognition,
                        embedding=embedding,
                        embedding_model=embedding_model,
                        embedding_dimensions=settings.ai_embedding_dimensions if embedding else None,
                        embedding_status=embedding_status,
                        embedding_source_hash=hashlib.sha256(embedding_text.encode()).hexdigest(),
                        embedding_updated_at=datetime.now(timezone.utc) if embedding else None,
                    )
                )

            else:
                info = _probe_video(local_path)
                if not info["has_video"] or info["duration"] <= 0:
                    raise RuntimeError("未检测到有效视频流")
                asset.duration_ms = round(info["duration"] * 1000)
                asset.width = info["width"]
                asset.height = info["height"]
                asset.fps = info["fps"]
                asset.codec = info["codec"]
                asset.has_audio = info["has_audio"]
                asset.audio_codec = info["audio_codec"]
                asset.sample_rate = info["sample_rate"]
                asset.channels = info["channels"]
                asset.bitrate = info["bitrate"]

                await _update_job(job_id, stage="视频代理转码", progress=15)
                proxy_local = os.path.join(temp_dir, "preview.mp4")
                _transcode_video_proxy(local_path, proxy_local)
                preview_path = f"video-previews/{asset.id}/preview.mp4"
                with open(proxy_local, "rb") as stream:
                    upload_stream(
                        preview_path,
                        stream,
                        os.path.getsize(proxy_local),
                        "video/mp4",
                    )
                asset.preview_path = preview_path

                await _update_job(job_id, stage="语音转写", progress=30)
                if asset.has_audio:
                    try:
                        if settings.ai_asr_provider.lower() == "local":
                            wav_path = os.path.join(temp_dir, "asr.wav")
                            _extract_audio(local_path, wav_path)
                            asset.transcript = await transcribe_audio(local_path=wav_path)
                        else:
                            asset.transcript = await transcribe_audio(
                                audio_url=get_file_url(asset.file_path, expires_hours=2)
                            )
                    except Exception:
                        asset.transcript = ""

                await _update_job(job_id, stage="OCR", progress=48)
                frames_dir = os.path.join(temp_dir, "frames")
                os.makedirs(frames_dir, exist_ok=True)
                frames = _extract_keyframes(local_path, frames_dir)
                observations: list[tuple[int, str]] = []
                for index, frame in enumerate(frames):
                    try:
                        text = await _recognize_image(frame)
                        if text.strip():
                            observations.append((index * 10000, text.strip()))
                    except Exception:
                        continue
                asset.ocr_text = "\n".join(dict.fromkeys(text for _, text in observations))
                words = [
                    value for value in re.split(r"[\s,，。、！？：:;；]+", asset.ocr_text or "")
                    if len(value) >= 2
                ]
                asset.tags = words[:20]

                await _update_job(job_id, stage="镜头切分", progress=65)
                scenes = _detect_scenes(local_path, info["duration"])
                segment_drafts: list[dict] = []
                for index, (start, end) in enumerate(scenes):
                    start_ms, end_ms = round(start * 1000), round(end * 1000)
                    transcript = ""
                    if asset.transcript and asset.duration_ms:
                        text_start = round(start_ms / asset.duration_ms * len(asset.transcript))
                        text_end = round(end_ms / asset.duration_ms * len(asset.transcript))
                        transcript = asset.transcript[text_start:text_end].strip()
                    ocr_text = "\n".join(
                        dict.fromkeys(text for timestamp, text in observations if start_ms <= timestamp < end_ms)
                    )
                    thumbnail_path = None
                    thumbnail_local = None
                    try:
                        thumbnail_local = os.path.join(temp_dir, f"thumb-{index}.jpg")
                        _extract_thumbnail(local_path, (start + end) / 2, thumbnail_local)
                        thumbnail_path = f"thumbnails/{asset.id}/{index:04d}.jpg"
                        with open(thumbnail_local, "rb") as stream:
                            upload_file(thumbnail_path, stream.read(), "image/jpeg")
                        if index == 0:
                            asset.thumbnail_path = thumbnail_path
                    except Exception:
                        pass
                    segment_drafts.append({
                        "index": index,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "transcript": transcript,
                        "ocr_text": ocr_text,
                        "thumbnail_path": thumbnail_path,
                        "thumbnail_local": thumbnail_local if thumbnail_local and os.path.exists(thumbnail_local) else None,
                    })

                await _update_job(job_id, stage="视觉理解", progress=78)
                visual_inputs = [
                    {
                        "index": draft["index"],
                        "local_path": draft["thumbnail_local"],
                        "transcript": draft["transcript"],
                        "ocr": draft["ocr_text"],
                    }
                    for draft in segment_drafts if draft["thumbnail_local"]
                ]
                visual_failure = ""
                try:
                    visual_by_index = await _visual_recognitions(visual_inputs) if visual_inputs else {}
                except Exception as exc:
                    visual_by_index = {}
                    visual_failure = str(exc)[:300]

                completed_recognitions: list[dict] = []
                for draft in segment_drafts:
                    index = draft["index"]
                    recognition = visual_by_index.get(index, {
                        "analysis_status": "failed" if settings.has_vision else "disabled",
                        "summary": "",
                        "error": visual_failure or "没有可用代表帧",
                    })
                    if "analysis_status" not in recognition:
                        recognition["analysis_status"] = "ready"
                    if recognition.get("analysis_status") == "ready":
                        completed_recognitions.append(recognition)
                    segment_tags = list(dict.fromkeys([*(asset.tags or []), *_recognition_tags(recognition)]))[:20]
                    embedding_text = " ".join(
                        value for value in (
                            draft["transcript"],
                            draft["ocr_text"],
                            str(recognition.get("summary") or ""),
                            " ".join(segment_tags),
                        ) if value
                    )
                    embedding, embedding_status, embedding_model = await _embedding(embedding_text)
                    session.add(
                        AssetSegment(
                            asset_id=asset.id,
                            start_ms=draft["start_ms"],
                            end_ms=draft["end_ms"],
                            title=(str(recognition.get("summary") or "").strip()[:120] or f"片段 {index + 1}"),
                            transcript=draft["transcript"],
                            ocr_text=draft["ocr_text"],
                            tags=segment_tags,
                            recognition=recognition,
                            thumbnail_path=draft["thumbnail_path"],
                            embedding=embedding,
                            embedding_model=embedding_model,
                            embedding_dimensions=settings.ai_embedding_dimensions if embedding else None,
                            embedding_status=embedding_status,
                            embedding_source_hash=hashlib.sha256(embedding_text.encode()).hexdigest() if embedding_text else None,
                            embedding_updated_at=datetime.now(timezone.utc) if embedding else None,
                            quality_score=float((recognition.get("quality") or {}).get("usable_score") or 0),
                        )
                    )
                asset.recognition = _aggregate_recognition(
                    completed_recognitions,
                    "ready" if completed_recognitions else ("failed" if settings.has_vision else "disabled"),
                )
                if visual_failure:
                    asset.recognition["error"] = visual_failure
                asset.tags = list(dict.fromkeys([*(asset.tags or []), *(asset.recognition.get("tags") or [])]))[:20]

            asset.status = "ready"
            asset.processing_status = "ready"
            await session.commit()
            completed = await _update_job(
                job_id,
                status="SUCCEEDED",
                stage="完成",
                progress=100,
                detail=f"{asset.name} 处理完成",
                result="已进入素材库",
                result_detail="素材已经可以在全局素材库中检索和使用",
            )
            if completed:
                await _broadcast_ws(owner_id, {"job_id": job_id, "status": "SUCCEEDED", "progress": 100})
    except Exception as exc:
        async with async_session_factory() as session:
            asset = await session.get(Asset, asset_id)
            if asset:
                asset.status = "failed"
                asset.processing_status = "failed"
                await session.commit()
        await _update_job(
            job_id,
            status="FAILED",
            stage="处理失败",
            detail=str(exc)[:500],
            result=None,
            result_detail=str(exc)[:500],
        )
        await _broadcast_ws(owner_id, {"job_id": job_id, "status": "FAILED", "progress": 0})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@celery_app.task(bind=True, name="app.tasks.retry_asset_processing")
def retry_asset_processing(self, job_id: str):
    run_async(_retry_asset_processing_async(job_id))


async def _retry_asset_processing_async(job_id: str) -> None:
    from app.database import async_session_factory
    from app.models.job import Job

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        if not job or not (job.payload or {}).get("asset_id"):
            return
        await _process_asset_async(job.payload["asset_id"], job.id)
