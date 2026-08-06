"""基于持久化时间线的真实 FFmpeg 导出任务。"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app
from app.services.timeline_validation import TimelineValidationError, validate_project_timeline


def _run_command(cmd: list[str], label: str, timeout: int = 600) -> None:
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace")[-600:]
        raise RuntimeError(f"{label}失败：{detail}")


def _has_audio(file_path: str, ffprobe: str) -> bool:
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            file_path,
        ],
        capture_output=True,
        timeout=60,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _float(value: Any, default: float) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _video_filter(clip: dict, target_w: int, target_h: int, duration: float) -> str:
    transform = clip.get("transform") or {}
    crop = transform.get("crop") or {}
    adjust = clip.get("adjust") or {}
    transition = clip.get("transition") or {}

    crop_l = max(0.0, min(99.0, _float(crop.get("l"), 0.0)))
    crop_r = max(0.0, min(99.0, _float(crop.get("r"), 0.0)))
    crop_t = max(0.0, min(99.0, _float(crop.get("t"), 0.0)))
    crop_b = max(0.0, min(99.0, _float(crop.get("b"), 0.0)))
    if crop_l + crop_r >= 100 or crop_t + crop_b >= 100:
        raise RuntimeError(f"片段「{clip.get('name', '未命名')}」的裁剪范围无效")

    scale = max(0.01, _float(transform.get("scale"), 100.0) / 100.0)
    position_x = max(-5.0, min(5.0, _float(transform.get("x"), 0.0) / 100.0))
    position_y = max(-5.0, min(5.0, _float(transform.get("y"), 0.0) / 100.0))
    rotation = math.radians(_float(transform.get("rotation"), 0.0))
    opacity = max(0.0, min(1.0, _float(transform.get("opacity"), 100.0) / 100.0))

    brightness = max(-1.0, min(1.0, (_float(adjust.get("brightness"), 100.0) - 100.0) / 100.0))
    contrast = max(0.0, min(3.0, _float(adjust.get("contrast"), 100.0) / 100.0))
    saturation = max(0.0, min(3.0, _float(adjust.get("saturation"), 100.0) / 100.0))

    crop_w = (100.0 - crop_l - crop_r) / 100.0
    crop_h = (100.0 - crop_t - crop_b) / 100.0
    filters = []
    if clip.get("generated_media_type") == "video":
        filters.append(f"tpad=stop_mode=clone:stop_duration={duration:.6f}")
    filters.extend([
        f"trim=duration={duration:.6f}",
        "setpts=PTS-STARTPTS",
        (
            f"crop=iw*{crop_w:.6f}:ih*{crop_h:.6f}:"
            f"iw*{crop_l / 100.0:.6f}:ih*{crop_t / 100.0:.6f}"
        ),
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease",
        f"eq=brightness={brightness:.6f}:contrast={contrast:.6f}:saturation={saturation:.6f}",
        "format=rgba",
        f"rotate={rotation:.8f}:ow=rotw(iw):oh=roth(ih):c=none",
        f"scale=trunc(iw*{scale:.6f}/2)*2:trunc(ih*{scale:.6f}/2)*2",
        f"colorchannelmixer=aa={opacity:.6f}",
    ])
    overlay_x = f"(main_w-overlay_w)/2+main_w*{position_x:.6f}"
    overlay_y = f"(main_h-overlay_h)/2+main_h*{position_y:.6f}"
    transition_type = str(transition.get("type") or "none")
    transition_duration = min(
        3.0,
        duration / 2.0,
        max(0.1, _float(transition.get("duration"), 0.5)),
    )
    post_filters = []
    if transition_type in {"fade_black", "fade_white"}:
        color = "white" if transition_type == "fade_white" else "black"
        post_filters.extend([
            f"fade=t=in:st=0:d={transition_duration:.6f}:color={color}",
            f"fade=t=out:st={max(0.0, duration - transition_duration):.6f}:d={transition_duration:.6f}:color={color}",
        ])
    post_filters.append("format=yuv420p")
    return (
        f"[0:v]{','.join(filters)}[foreground];"
        f"[1:v][foreground]overlay=x='{overlay_x}':y='{overlay_y}':"
        f"eof_action=pass:shortest=0[composited];[composited]{','.join(post_filters)}[video_out]"
    )


def _render_gap(
    ffmpeg: str,
    output_path: str,
    duration: float,
    target_w: int,
    target_h: int,
) -> None:
    _run_command(
        [
            ffmpeg,
            "-f", "lavfi", "-i", f"color=c=black:s={target_w}x{target_h}:r=25",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t", f"{duration:.6f}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
            "-y", output_path,
        ],
        "空白时间段渲染",
    )


def _render_video_segment(
    ffmpeg: str,
    ffprobe: str,
    clip: dict,
    output_path: str,
    target_w: int,
    target_h: int,
) -> None:
    duration = _float(clip.get("duration"), 0.0)
    source_start = _float(clip.get("source_start"), 0.0)
    source_path = str(clip["source_path"])
    audio = clip.get("audio") or {}
    volume = max(0.0, min(2.0, _float(audio.get("volume"), 100.0) / 100.0))
    if audio.get("muted"):
        volume = 0.0
    denoise = bool(audio.get("denoise", False))
    fade_in = min(duration / 2.0, max(0.0, _float(audio.get("fade_in"), 0.0)))
    fade_out = min(duration / 2.0, max(0.0, _float(audio.get("fade_out"), 0.0)))
    transition = clip.get("transition") or {}
    source_has_audio = _has_audio(source_path, ffprobe)

    if clip.get("generated_media_type") == "image":
        cmd = [ffmpeg, "-loop", "1", "-i", source_path]
    else:
        cmd = [ffmpeg, "-ss", f"{source_start:.6f}", "-i", source_path]
    cmd.extend([
        "-f", "lavfi", "-i", f"color=c=black:s={target_w}x{target_h}:r=25:d={duration:.6f}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
    ])

    filter_complex = _video_filter(clip, target_w, target_h, duration)
    if source_has_audio:
        audio_filters = [
            f"atrim=duration={duration:.6f}",
            "asetpts=PTS-STARTPTS",
        ]
        if denoise:
            audio_filters.append("afftdn=nf=-25")
        if fade_in > 0:
            audio_filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            audio_filters.append(
                f"afade=t=out:st={max(0.0, duration - fade_out):.6f}:d={fade_out:.6f}"
            )
        transition_type = str(transition.get("type") or "none")
        if transition_type != "none":
            transition_duration = min(
                3.0,
                duration / 2.0,
                max(0.1, _float(transition.get("duration"), 0.5)),
            )
            audio_filters.extend([
                f"afade=t=in:st=0:d={transition_duration:.6f}",
                f"afade=t=out:st={max(0.0, duration - transition_duration):.6f}:d={transition_duration:.6f}",
            ])
        audio_filters.extend([
            f"volume={volume:.6f}",
            f"apad=pad_dur={duration:.6f}",
            f"atrim=duration={duration:.6f}",
        ])
        filter_complex += f";[0:a]{','.join(audio_filters)}[audio_out]"
        audio_map = "[audio_out]"
    else:
        audio_map = "2:a:0"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[video_out]", "-map", audio_map,
        "-t", f"{duration:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        "-y", output_path,
    ])
    _run_command(cmd, f"片段「{clip.get('name', '未命名')}」渲染")


def _mix_audio_tracks(
    ffmpeg: str,
    ffprobe: str,
    rendered_file: str,
    audio_clips: list[dict],
    output_path: str,
    duration: float,
) -> None:
    if not audio_clips:
        shutil.copy2(rendered_file, output_path)
        return

    cmd = [ffmpeg, "-i", rendered_file]
    filter_parts = ["[0:a]volume=1[base_audio]"]
    mix_inputs = ["[base_audio]"]
    for index, clip in enumerate(audio_clips, start=1):
        source_path = str(clip["source_path"])
        if not _has_audio(source_path, ffprobe):
            raise RuntimeError(f"音频轨素材「{clip.get('name', '未命名')}」没有可用音轨")
        source_start = _float(clip.get("source_start"), 0.0)
        clip_duration = _float(clip.get("duration"), 0.0)
        timeline_start = _float(clip.get("start"), 0.0)
        audio = clip.get("audio") or {}
        volume = max(0.0, min(2.0, _float(audio.get("volume"), 100.0) / 100.0))
        if audio.get("muted"):
            volume = 0.0
        denoise = bool(audio.get("denoise", False))
        fade_in = min(clip_duration / 2.0, max(0.0, _float(audio.get("fade_in"), 0.0)))
        fade_out = min(clip_duration / 2.0, max(0.0, _float(audio.get("fade_out"), 0.0)))
        cmd.extend(["-ss", f"{source_start:.6f}", "-i", source_path])
        filters = [
            f"atrim=duration={clip_duration:.6f}",
            f"asetpts=PTS-STARTPTS+{timeline_start:.6f}/TB",
        ]
        if denoise:
            filters.append("afftdn=nf=-25")
        if fade_in > 0:
            filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            filters.append(
                f"afade=t=out:st={max(0.0, clip_duration - fade_out):.6f}:d={fade_out:.6f}"
            )
        filters.append(f"volume={volume:.6f}")
        label = f"audio_{index}"
        filter_parts.append(f"[{index}:a]{','.join(filters)}[{label}]")
        mix_inputs.append(f"[{label}]")

    filter_parts.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:"
        "dropout_transition=0:normalize=0,alimiter=limit=0.95[audio_out]"
    )
    cmd.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v:0", "-map", "[audio_out]",
        "-t", f"{duration:.6f}",
        "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
        "-y", output_path,
    ])
    _run_command(cmd, "多音轨混合")


def _font_path(configured: str) -> str:
    candidates = [
        configured,
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError("没有可用的字幕字体，请配置 SUBTITLE_FONT_PATH")


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.replace("\r", "").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for character in paragraph:
            candidate = current + character
            width = draw.textbbox((0, 0), candidate, font=font, stroke_width=1)[2]
            if current and width > max_width:
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines[:4]


def _render_subtitle_image(
    text: str,
    output_path: str,
    target_w: int,
    target_h: int,
    configured_font: str,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    strip_h = max(120, target_h // 4)
    image = Image.new("RGBA", (target_w, strip_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_size = max(24, min(72, target_h // 16))
    font = ImageFont.truetype(_font_path(configured_font), font_size)
    lines = _wrap_text(draw, text.strip(), font, int(target_w * 0.82))
    rendered_text = "\n".join(lines)
    bbox = draw.multiline_textbbox(
        (0, 0), rendered_text, font=font, spacing=max(4, font_size // 5),
        align="center", stroke_width=max(1, font_size // 24),
    )
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    padding_x = max(18, font_size // 2)
    padding_y = max(10, font_size // 4)
    left = max(8, (target_w - text_w) // 2 - padding_x)
    top = max(4, (strip_h - text_h) // 2 - padding_y)
    right = min(target_w - 8, (target_w + text_w) // 2 + padding_x)
    bottom = min(strip_h - 4, (strip_h + text_h) // 2 + padding_y)
    draw.rounded_rectangle((left, top, right, bottom), radius=max(8, font_size // 4), fill=(0, 0, 0, 155))
    draw.multiline_text(
        (target_w // 2, strip_h // 2),
        rendered_text,
        font=font,
        fill=(255, 255, 255, 255),
        anchor="mm",
        align="center",
        spacing=max(4, font_size // 5),
        stroke_width=max(1, font_size // 24),
        stroke_fill=(0, 0, 0, 220),
    )
    image.save(output_path, "PNG")


def _burn_subtitles(
    ffmpeg: str,
    source_file: str,
    entries: list[dict],
    output_path: str,
    temp_dir: str,
    target_w: int,
    target_h: int,
    duration: float,
    configured_font: str,
) -> None:
    if not entries:
        shutil.copy2(source_file, output_path)
        return

    cmd = [ffmpeg, "-i", source_file]
    valid_entries: list[tuple[dict, str]] = []
    for index, entry in enumerate(entries):
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        image_path = os.path.join(temp_dir, f"subtitle_{index:04d}.png")
        _render_subtitle_image(text, image_path, target_w, target_h, configured_font)
        cmd.extend(["-loop", "1", "-framerate", "25", "-i", image_path])
        valid_entries.append((entry, image_path))

    if not valid_entries:
        shutil.copy2(source_file, output_path)
        return

    filters: list[str] = []
    current = "0:v"
    bottom_margin = max(16, target_h // 24)
    for input_index, (entry, _) in enumerate(valid_entries, start=1):
        start = max(0.0, _float(entry.get("start"), 0.0))
        end = min(duration, start + max(0.0, _float(entry.get("duration"), 0.0)))
        label = f"subtitle_video_{input_index}"
        filters.append(
            f"[{current}][{input_index}:v]overlay=x=0:y=main_h-overlay_h-{bottom_margin}:"
            f"enable='between(t,{start:.6f},{end:.6f})':eof_action=pass[{label}]"
        )
        current = label

    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]", "-map", "0:a:0",
        "-t", f"{duration:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-y", output_path,
    ])
    _run_command(cmd, "字幕烧录")


@celery_app.task(bind=True, name="app.tasks.export_project")
def export_project(self, project_id: str, job_id: str, format: str = "mp4", resolution: str = "1080p"):
    run_async(_export_project_async(project_id, job_id, format, resolution))


async def _export_project_async(project_id: str, job_id: str, format: str, resolution: str):
    from sqlalchemy import select, update

    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.asset import Asset
    from app.models.job import Job
    from app.models.notification import Notification
    from app.models.project import Project
    from app.models.user import Usage
    from app.utils.storage import download_file, get_file_url, upload_stream

    settings = get_settings()
    ffmpeg = settings.ffmpeg_path
    ffprobe = settings.ffprobe_path
    resolution_map = {
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "4k": (3840, 2160),
    }
    target_w, target_h = resolution_map.get(resolution, (1920, 1080))
    extension = "mp4" if format == "mp4" else "mov"
    stages = ["准备时间线", "渲染视频轨", "混合音频轨", "烧录字幕", "编码输出"]
    temp_dir = tempfile.mkdtemp(prefix=f"export_{project_id}_")

    try:
        async with async_session_factory() as session:
            project = await session.get(Project, project_id)
            if not project:
                raise RuntimeError("项目不存在")

            timeline = project.timeline or []
            try:
                await validate_project_timeline(project, timeline, session)
            except TimelineValidationError as exc:
                raise RuntimeError(f"时间线校验失败：{exc}") from exc
            video_clips = sorted(
                [
                    dict(item)
                    for item in timeline
                    if item.get("track") == "video"
                    and (item.get("asset_id") or item.get("generated_media_path"))
                ],
                key=lambda item: _float(item.get("start"), 0.0),
            )
            audio_clips = sorted(
                [dict(item) for item in timeline if item.get("track") == "audio" and item.get("asset_id")],
                key=lambda item: _float(item.get("start"), 0.0),
            )
            subtitle_entries = [
                {
                    "text": item.get("text"),
                    "start": item.get("start", 0),
                    "duration": item.get("duration", 0),
                }
                for item in timeline
                if item.get("text") and item.get("track") in {"subtitle", "video"}
            ]
            if not video_clips:
                raise RuntimeError("时间线中没有可渲染的视频素材")

            media_paths: dict[str, str] = {}
            for clip in video_clips + audio_clips:
                generated_path = clip.get("generated_media_path")
                if generated_path:
                    media_key = f"generated:{generated_path}"
                    if media_key not in media_paths:
                        suffix = Path(str(generated_path)).suffix or (
                            ".jpg" if clip.get("generated_media_type") == "image" else ".mp4"
                        )
                        local_path = os.path.join(temp_dir, f"generated_{len(media_paths):04d}{suffix}")
                        download_file(str(generated_path), local_path)
                        media_paths[media_key] = local_path
                    clip["source_path"] = media_paths[media_key]
                    continue

                asset_id = str(clip.get("asset_id"))
                asset = await session.get(Asset, asset_id)
                if not asset or not asset.file_path:
                    raise RuntimeError(f"时间线素材不可用：{clip.get('name', asset_id)}")
                source_start = _float(clip.get("source_start"), 0.0)
                clip_duration = _float(clip.get("duration"), 0.0)
                if source_start < 0 or clip_duration <= 0:
                    raise RuntimeError(f"时间线片段范围无效：{clip.get('name', asset.name)}")
                if asset.duration > 0 and source_start + clip_duration > asset.duration + 0.05:
                    raise RuntimeError(
                        f"片段「{clip.get('name', asset.name)}」超出源素材时长，请缩短片段后重试"
                    )
                media_key = f"asset:{asset_id}"
                if media_key not in media_paths:
                    suffix = Path(asset.file_path).suffix or ".media"
                    local_path = os.path.join(temp_dir, f"asset_{len(media_paths):04d}{suffix}")
                    download_file(asset.file_path, local_path)
                    media_paths[media_key] = local_path
                clip["source_path"] = media_paths[media_key]

            timeline_duration = max(
                _float(clip.get("start"), 0.0) + _float(clip.get("duration"), 0.0)
                for clip in video_clips
            )
            cursor = 0.0
            for clip in video_clips:
                start = _float(clip.get("start"), 0.0)
                if start < cursor - 0.01:
                    raise RuntimeError("视频轨存在重叠片段；当前导出仅支持单视频轨不重叠排列")
                cursor = start + _float(clip.get("duration"), 0.0)

            rendered_file = os.path.join(temp_dir, "rendered.mp4")
            mixed_file = os.path.join(temp_dir, "mixed.mp4")
            subtitled_file = os.path.join(temp_dir, "subtitled.mp4")

            for stage_index, stage in enumerate(stages):
                await session.execute(
                    update(Job).where(Job.id == job_id).values(
                        status="RUNNING",
                        stage=stage,
                        stage_index=stage_index,
                        progress=int(stage_index / len(stages) * 100),
                        detail=f"正在{stage}",
                        result=None,
                        result_detail="",
                        result_url=None,
                        result_path=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

                if stage_index == 1:
                    segment_files: list[str] = []
                    cursor = 0.0
                    for index, clip in enumerate(video_clips):
                        start = _float(clip.get("start"), 0.0)
                        if start - cursor > 0.01:
                            gap_file = os.path.join(temp_dir, f"segment_{len(segment_files):04d}_gap.mp4")
                            _render_gap(ffmpeg, gap_file, start - cursor, target_w, target_h)
                            segment_files.append(gap_file)
                        segment_file = os.path.join(temp_dir, f"segment_{len(segment_files):04d}.mp4")
                        _render_video_segment(ffmpeg, ffprobe, clip, segment_file, target_w, target_h)
                        segment_files.append(segment_file)
                        cursor = start + _float(clip.get("duration"), 0.0)

                    concat_list = os.path.join(temp_dir, "concat_list.txt")
                    with open(concat_list, "w", encoding="utf-8") as handle:
                        for segment_file in segment_files:
                            handle.write(f"file '{segment_file}'\n")
                    _run_command(
                        [
                            ffmpeg, "-f", "concat", "-safe", "0", "-i", concat_list,
                            "-c", "copy", "-y", rendered_file,
                        ],
                        "片段合并",
                    )

                elif stage_index == 2:
                    _mix_audio_tracks(
                        ffmpeg, ffprobe, rendered_file, audio_clips, mixed_file, timeline_duration
                    )

                elif stage_index == 3:
                    _burn_subtitles(
                        ffmpeg,
                        mixed_file,
                        subtitle_entries,
                        subtitled_file,
                        temp_dir,
                        target_w,
                        target_h,
                        timeline_duration,
                        settings.subtitle_font_path,
                    )

                elif stage_index == 4:
                    final_file = os.path.join(temp_dir, f"output.{extension}")
                    if format == "mp4":
                        shutil.copy2(subtitled_file, final_file)
                    elif format == "mov":
                        _run_command(
                            [ffmpeg, "-i", subtitled_file, "-c", "copy", "-f", "mov", "-y", final_file],
                            "MOV 封装",
                        )
                    elif format == "prores":
                        _run_command(
                            [
                                ffmpeg, "-i", subtitled_file,
                                "-c:v", "prores_ks", "-profile:v", "2",
                                "-c:a", "pcm_s16le", "-y", final_file,
                            ],
                            "ProRes 编码",
                            timeout=1800,
                        )
                    else:
                        raise RuntimeError(f"不支持的导出格式：{format}")

                    object_name = f"exports/{project_id}/{job_id}.{extension}"
                    content_type = "video/mp4" if extension == "mp4" else "video/quicktime"
                    with open(final_file, "rb") as output_stream:
                        upload_stream(
                            object_name,
                            output_stream,
                            os.path.getsize(final_file),
                            content_type,
                        )
                    export_url = get_file_url(object_name)

                    usage = (
                        await session.execute(select(Usage).where(Usage.user_id == project.owner_id))
                    ).scalar_one_or_none()
                    if usage:
                        usage.export_used += 1
                    await session.execute(
                        update(Job).where(Job.id == job_id).values(
                            status="SUCCEEDED",
                            progress=100,
                            stage="完成",
                            detail=f"导出完成：{format} {resolution}",
                            result="查看结果",
                            result_detail="成片已按持久化时间线和编辑参数导出",
                            result_url=export_url,
                            result_path=object_name,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    existing_notification = (
                        await session.execute(
                            select(Notification.id).where(
                                Notification.job_id == job_id,
                                Notification.type == "export",
                            )
                        )
                    ).scalar_one_or_none()
                    if not existing_notification:
                        session.add(
                            Notification(
                                user_id=project.owner_id,
                                project_id=project.id,
                                job_id=job_id,
                                type="export",
                                title="视频导出完成",
                                message=f"{project.name} 已完成 {format} {resolution} 导出",
                                link=f"/workspace/projects/{project.id}/editor?exportJob={job_id}",
                            )
                        )
                    await session.commit()

    except Exception as exc:
        async with async_session_factory() as failure_session:
            from sqlalchemy import update

            from app.models.job import Job

            message = str(exc)[:600]
            await failure_session.execute(
                update(Job).where(Job.id == job_id).values(
                    status="FAILED",
                    stage="导出失败",
                    detail=f"导出失败：{message}",
                    result=None,
                    result_detail=message,
                    result_url=None,
                    result_path=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await failure_session.commit()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
