"""从唯一主脚本、镜头和 Composition 即时编译的真实 FFmpeg 导出任务。"""

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
from app.services.quotas import complete_job_success
from app.services.composition_render_plan import compile_composition_render_plan


def _target_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    """Resolve an even output size from the composition aspect ratio."""
    landscape = {
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "4k": (3840, 2160),
    }
    width, height = landscape.get(resolution, landscape["1080p"])
    dimensions = {
        "16:9": (width, height),
        "9:16": (height, width),
        "1:1": (height, height),
        "4:3": (height * 4 // 3, height),
    }
    output_w, output_h = dimensions.get(aspect_ratio, dimensions["16:9"])
    return output_w // 2 * 2, output_h // 2 * 2


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
    motion = clip.get("motion") or {}
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
    rotation = math.radians(_float(transform.get("rotate", transform.get("rotation")), 0.0))
    opacity = max(0.0, min(1.0, _float(transform.get("opacity"), 100.0) / 100.0))

    preset = str(adjust.get("filterPreset") or adjust.get("filter_preset") or "original")
    preset_grade = {
        "cinematic": (0.0, 0.12, -0.10, 0.0),
        "vivid": (0.0, 0.08, 0.30, 0.0),
        "warm": (0.02, 0.02, 0.08, 8.0),
        "cool": (-0.01, 0.02, -0.12, -8.0),
        "monochrome": (0.0, 0.08, -1.0, 0.0),
        "vintage": (-0.01, -0.06, -0.18, 7.0),
        "cyber": (0.0, 0.18, 0.38, 12.0),
    }.get(preset, (0.0, 0.0, 0.0, 0.0))
    brightness = max(-1.0, min(1.0, _float(adjust.get("brightness"), 0.0) / 100.0 + preset_grade[0]))
    contrast = max(0.0, min(3.0, 1.0 + _float(adjust.get("contrast"), 0.0) / 100.0 + preset_grade[1]))
    saturation = max(0.0, min(3.0, 1.0 + _float(adjust.get("saturation"), 0.0) / 100.0 + preset_grade[2]))
    hue = max(-180.0, min(180.0, _float(adjust.get("hue"), 0.0) + preset_grade[3]))
    temperature = max(-100.0, min(100.0, _float(adjust.get("temperature"), 0.0)))
    grayscale = max(0.0, min(1.0, _float(adjust.get("grayscale"), 0.0) / 100.0))
    if preset == "monochrome":
        grayscale = 1.0
    saturation *= 1.0 - grayscale

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
        (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
            if str(transform.get("fitMode") or transform.get("fit_mode") or "cover") == "cover"
            else f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        ),
        f"eq=brightness={brightness:.6f}:contrast={contrast:.6f}:saturation={saturation:.6f}",
        f"hue=h={hue:.6f}",
        f"colorbalance=rs={temperature / 1000.0:.6f}:bs={-temperature / 1000.0:.6f}",
    ])
    motion_type = str(motion.get("type") or "none")
    strength = max(0.0, min(1.0, _float(motion.get("strength"), 40.0) / 100.0))
    frames = max(1, round(duration * max(1, int(clip.get("fps") or 25))))
    if motion_type in {"push", "pull", "pan-left", "pan-right", "tilt-up", "tilt-down"}:
        amount = 0.12 * strength
        if motion_type == "push":
            zoom = f"1+{amount:.6f}*on/{frames}"
            x = "(iw-iw/zoom)/2"
            y = "(ih-ih/zoom)/2"
        elif motion_type == "pull":
            zoom = f"1+{amount:.6f}*(1-on/{frames})"
            x = "(iw-iw/zoom)/2"
            y = "(ih-ih/zoom)/2"
        else:
            zoom = f"1+{max(0.02, amount):.6f}"
            progress = f"on/{frames}"
            x = "(iw-iw/zoom)/2"
            y = "(ih-ih/zoom)/2"
            if motion_type == "pan-left":
                x = f"(iw-iw/zoom)*(1-{progress})"
            elif motion_type == "pan-right":
                x = f"(iw-iw/zoom)*{progress}"
            elif motion_type == "tilt-up":
                y = f"(ih-ih/zoom)*(1-{progress})"
            elif motion_type == "tilt-down":
                y = f"(ih-ih/zoom)*{progress}"
        filters.append(
            f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={target_w}x{target_h}:fps={max(1, int(clip.get('fps') or 25))}"
        )
    rotation_filter = f"rotate={rotation:.8f}:ow=rotw(iw):oh=roth(ih):c=none"
    if motion_type == "handheld":
        rotation_filter = (
            f"rotate='{rotation:.8f}+sin(t*17)*{math.radians(0.5 * strength):.8f}':"
            "ow=rotw(iw):oh=roth(ih):c=none"
        )
    filters.extend([
        "format=rgba",
        rotation_filter,
        f"scale=trunc(iw*{scale:.6f}/2)*2:trunc(ih*{scale:.6f}/2)*2",
        f"colorchannelmixer=aa={opacity:.6f}",
    ])
    overlay_x = f"(main_w-overlay_w)/2+main_w*{position_x:.6f}"
    overlay_y = f"(main_h-overlay_h)/2+main_h*{position_y:.6f}"
    return (
        f"[0:v]{','.join(filters)}[foreground];"
        f"[1:v][foreground]overlay=x='{overlay_x}':y='{overlay_y}':"
        "eof_action=pass:shortest=0[composited];[composited]format=yuv420p[video_out]"
    )


def _render_gap(
    ffmpeg: str,
    output_path: str,
    duration: float,
    target_w: int,
    target_h: int,
    fps: int = 25,
) -> None:
    _run_command(
        [
            ffmpeg,
            "-f", "lavfi", "-i", f"color=c=black:s={target_w}x{target_h}:r={fps}",
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
    source_has_audio = _has_audio(source_path, ffprobe)

    fps = max(1, min(120, int(clip.get("fps") or 25)))
    if clip.get("generated_media_type") == "image":
        cmd = [ffmpeg, "-loop", "1", "-framerate", str(fps), "-i", source_path]
    else:
        cmd = [ffmpeg, "-ss", f"{source_start:.6f}", "-i", source_path]
    cmd.extend([
        "-f", "lavfi", "-i", f"color=c=black:s={target_w}x{target_h}:r={fps}:d={duration:.6f}",
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


def _apply_outgoing_transition(
    ffmpeg: str,
    ffprobe: str,
    current_file: str,
    current_clip: dict,
    next_clip: dict | None,
    output_path: str,
    temp_dir: str,
    target_w: int,
    target_h: int,
    fps: int = 25,
) -> None:
    """Blend the next shot's first rendered frame inside the current segment.

    Keeping the transition inside the current segment preserves the canonical
    timeline duration, matching the browser preview instead of shortening it
    like a conventional cross-shot xfade pipeline would.
    """
    transition = current_clip.get("transition") or {}
    transition_type = str(transition.get("type") or "cut")
    if next_clip is None or transition_type in {"cut", "none"}:
        shutil.copy2(current_file, output_path)
        return
    duration = _float(current_clip.get("duration"), 0.0)
    transition_duration = min(
        3.0,
        duration / 2.0,
        max(0.1, _float(transition.get("duration"), 0.5)),
    )
    frame_path = os.path.join(temp_dir, f"transition_frame_{current_clip['id']}.png")
    source_path = str(next_clip["source_path"])
    frame_cmd = [ffmpeg]
    if next_clip.get("generated_media_type") != "image":
        frame_cmd.extend(["-ss", f"{_float(next_clip.get('source_start'), 0.0):.6f}"])
    frame_cmd.extend(["-i", source_path, "-frames:v", "1", "-y", frame_path])
    _run_command(frame_cmd, "转场首帧提取")

    preview_clip = {
        **next_clip,
        "source_path": frame_path,
        "source_start": 0.0,
        "duration": duration,
        "generated_media_type": "image",
        "transition": {"type": "cut"},
        "motion": {"type": "none"},
        "audio": {"muted": True},
    }
    preview_path = os.path.join(temp_dir, f"transition_preview_{current_clip['id']}.mp4")
    _render_video_segment(
        ffmpeg, ffprobe, preview_clip, preview_path, target_w, target_h
    )
    xfade_type = {
        "fade": "fade",
        "dissolve": "fade",
        "slide-left": "slideleft",
        "slide-right": "slideright",
        "zoom": "zoomin",
    }.get(transition_type, "fade")
    offset = max(0.0, duration - transition_duration)
    _run_command(
        [
            ffmpeg, "-i", current_file, "-i", preview_path,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition={xfade_type}:duration={transition_duration:.6f}:"
            f"offset={offset:.6f},trim=duration={duration:.6f},setpts=PTS-STARTPTS[video_out]",
            "-map", "[video_out]", "-map", "0:a:0", "-t", f"{duration:.6f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-y", output_path,
        ],
        f"镜头「{current_clip.get('name', '未命名')}」转场渲染",
    )


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
        if clip.get("loop"):
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-ss", f"{source_start:.6f}", "-i", source_path])
        filters = [
            f"atrim=duration={clip_duration:.6f}",
            f"apad=pad_dur={clip_duration:.6f}",
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


def _apply_visual_layers(
    ffmpeg: str,
    source_file: str,
    visual_layers: list[dict],
    output_path: str,
    target_w: int,
    target_h: int,
    duration: float,
    fps: int = 25,
) -> None:
    if not visual_layers:
        shutil.copy2(source_file, output_path)
        return

    cmd = [ffmpeg, "-i", source_file]
    active_layers: list[dict] = []
    for layer in visual_layers:
        layer_duration = min(
            max(0.0, duration - _float(layer.get("start"), 0.0)),
            max(0.0, _float(layer.get("duration"), 0.0)),
        )
        if layer_duration <= 0:
            continue
        if layer.get("generated_media_type") == "image":
            cmd.extend(["-loop", "1", "-framerate", str(fps)])
        else:
            cmd.extend(["-stream_loop", "-1"])
        source_start = max(0.0, _float(layer.get("source_start"), 0.0))
        if source_start:
            cmd.extend(["-ss", f"{source_start:.6f}"])
        cmd.extend(["-i", str(layer["source_path"])])
        active_layers.append({**layer, "duration": layer_duration})

    if not active_layers:
        shutil.copy2(source_file, output_path)
        return

    filters: list[str] = []
    current = "0:v"
    for input_index, layer in enumerate(active_layers, start=1):
        start = max(0.0, _float(layer.get("start"), 0.0))
        layer_duration = _float(layer.get("duration"), 0.0)
        end = min(duration, start + layer_duration)
        raw_opacity = _float(layer.get("opacity"), 32.0)
        opacity = max(0.0, min(1.0, raw_opacity if raw_opacity <= 1 else raw_opacity / 100.0))
        fit_mode = str(layer.get("fitMode") or layer.get("fit_mode") or "cover")
        prepared = f"visual_prepared_{input_index}"
        if fit_mode == "contain":
            sizing = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black@0"
            )
        else:
            sizing = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h}"
            )
        filters.append(
            f"[{input_index}:v]trim=duration={layer_duration:.6f},setpts=PTS-STARTPTS+{start:.6f}/TB,"
            f"{sizing},format=rgba,colorchannelmixer=aa={opacity:.6f}[{prepared}]"
        )
        output = f"visual_composite_{input_index}"
        # The prototype accepts CSS blend-mode names. FFmpeg overlay is the
        # deterministic baseline; unsupported blend modes intentionally
        # normalize to normal instead of producing an invalid filter graph.
        filters.append(
            f"[{current}][{prepared}]overlay=x=0:y=0:enable='between(t,{start:.6f},{end:.6f})':"
            f"eof_action=pass[{output}]"
        )
        current = output

    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]", "-map", "0:a:0", "-t", f"{duration:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-y", output_path,
    ])
    _run_command(cmd, "共享视觉层渲染")


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
    settings: dict | None = None,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    settings = settings or {}
    requested_size = max(10, min(96, round(_float(settings.get("font_size"), 16.0))))
    font_size = max(18, min(160, round(requested_size * target_h / 540)))
    strip_h = max(font_size * 4, target_h // 5)
    image = Image.new("RGBA", (target_w, strip_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
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
    color = str(settings.get("color") or "#ffffff").strip().lstrip("#")
    try:
        if len(color) == 3:
            color = "".join(character * 2 for character in color)
        fill = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
    except (ValueError, IndexError):
        fill = (255, 255, 255, 255)
    draw.multiline_text(
        (target_w // 2, strip_h // 2),
        rendered_text,
        font=font,
        fill=fill,
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
    fps: int = 25,
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
        _render_subtitle_image(
            text, image_path, target_w, target_h, configured_font, entry.get("settings")
        )
        cmd.extend(["-loop", "1", "-framerate", str(fps), "-i", image_path])
        valid_entries.append((entry, image_path))

    if not valid_entries:
        shutil.copy2(source_file, output_path)
        return

    filters: list[str] = []
    current = "0:v"
    margin = max(16, target_h // 24)
    for input_index, (entry, _) in enumerate(valid_entries, start=1):
        start = max(0.0, _float(entry.get("start"), 0.0))
        end = min(duration, start + max(0.0, _float(entry.get("duration"), 0.0)))
        label = f"subtitle_video_{input_index}"
        position = str((entry.get("settings") or {}).get("position") or "bottom")
        overlay_y = {
            "top": str(margin),
            "center": "(main_h-overlay_h)/2",
            "bottom": f"main_h-overlay_h-{margin}",
        }.get(position, f"main_h-overlay_h-{margin}")
        filters.append(
            f"[{current}][{input_index}:v]overlay=x=0:y='{overlay_y}':"
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


def requires_export_watermark(membership_rank: int) -> bool:
    """Free exports carry the OpenVMA brand; paid plans export clean video."""
    return membership_rank <= 0


def _render_watermark_image(
    output_path: str,
    target_w: int,
    target_h: int,
    configured_font: str,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font_size = max(22, min(56, target_h // 24))
    font = ImageFont.truetype(_font_path(configured_font), font_size)
    text = "OpenVMA"
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, font_size // 28))
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    padding_x = max(16, font_size // 2)
    padding_y = max(9, font_size // 4)
    image = Image.new(
        "RGBA",
        (text_w + padding_x * 2, text_h + padding_y * 2),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1),
        radius=max(8, font_size // 3),
        fill=(10, 18, 32, 155),
        outline=(255, 255, 255, 55),
        width=max(1, target_w // 1200),
    )
    draw.text(
        (image.width // 2, image.height // 2),
        text,
        font=font,
        fill=(255, 255, 255, 225),
        anchor="mm",
        stroke_width=max(1, font_size // 28),
        stroke_fill=(0, 0, 0, 120),
    )
    image.save(output_path, "PNG")


def _apply_export_watermark(
    ffmpeg: str,
    source_file: str,
    output_path: str,
    temp_dir: str,
    target_w: int,
    target_h: int,
    duration: float,
    configured_font: str,
    enabled: bool,
    fps: int = 25,
) -> None:
    if not enabled:
        shutil.copy2(source_file, output_path)
        return

    watermark_path = os.path.join(temp_dir, "openvma_watermark.png")
    _render_watermark_image(watermark_path, target_w, target_h, configured_font)
    margin = max(16, target_h // 36)
    _run_command(
        [
            ffmpeg,
            "-i", source_file,
            "-loop", "1", "-framerate", str(fps), "-i", watermark_path,
            "-filter_complex",
            f"[0:v][1:v]overlay=main_w-overlay_w-{margin}:main_h-overlay_h-{margin}:"
            "eof_action=pass[video_out]",
            "-map", "[video_out]", "-map", "0:a:0",
            "-t", f"{duration:.6f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-y", output_path,
        ],
        "OpenVMA 水印烧录",
    )


@celery_app.task(bind=True, name="app.tasks.export_project")
def export_project(
    self,
    project_id: str,
    job_id: str,
    format: str = "mp4",
    resolution: str = "1080p",
    aspect_ratio: str | None = None,
):
    run_async(_export_project_async(project_id, job_id, format, resolution, aspect_ratio))


async def _export_project_async(
    project_id: str,
    job_id: str,
    format: str,
    resolution: str,
    aspect_ratio: str | None = None,
):
    from sqlalchemy import select, update

    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.asset import Asset, AssetSegment
    from app.models.job import Job
    from app.models.notification import Notification
    from app.models.asset import ProjectAssetLink
    from app.models.user import User
    from app.services.subscriptions import reconcile_user_subscription
    from app.services.workspace import load_project_workspace, record_revision
    from app.services.storage_usage import recalculate_storage_usage
    from app.utils.storage import download_file, get_file_url, upload_stream
    from sqlalchemy.orm import selectinload

    settings = get_settings()
    ffmpeg = settings.ffmpeg_path
    ffprobe = settings.ffprobe_path
    extension = "mp4" if format == "mp4" else "mov"
    stages = ["准备时间线", "渲染视频轨", "叠加共享视觉层", "混合音频轨", "烧录字幕", "添加品牌水印", "编码输出"]
    temp_dir = tempfile.mkdtemp(prefix=f"export_{project_id}_")

    try:
        async with async_session_factory() as session:
            job = await session.get(Job, job_id)
            if not job:
                raise RuntimeError("导出任务不存在")
            project = await load_project_workspace(
                session, project_id, job.owner_id, for_update=True
            )
            base_revision = int((job.payload or {}).get("base_revision", project.script.revision))
            if project.script.revision != base_revision:
                raise RuntimeError("项目已继续编辑，本次导出基线已过期，请重新导出")
            owner = (
                await session.execute(
                    select(User)
                    .where(User.id == project.owner_id)
                    .options(
                        selectinload(User.membership),
                        selectinload(User.subscription),
                    )
                )
            ).scalar_one()
            await reconcile_user_subscription(session, owner)
            watermark_required = requires_export_watermark(
                owner.membership.rank if owner.membership else 0
            )

            render_plan = compile_composition_render_plan(project)
            video_clips = render_plan.video_clips
            audio_clips = render_plan.audio_clips
            subtitle_entries = render_plan.subtitle_entries
            visual_layers = render_plan.visual_layers
            export_aspect_ratio = aspect_ratio or render_plan.aspect_ratio
            target_w, target_h = _target_dimensions(resolution, export_aspect_ratio)
            output_fps = render_plan.fps
            if not video_clips:
                raise RuntimeError("时间线中没有可渲染的视频素材")

            media_paths: dict[str, str] = {}
            for clip in video_clips + audio_clips + visual_layers:
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
                    raise RuntimeError(f"项目素材不可用：{clip.get('name', asset_id)}")
                source_start = _float(clip.get("source_start"), 0.0)
                clip_duration = _float(clip.get("duration"), 0.0)
                if source_start < 0 or clip_duration <= 0:
                    raise RuntimeError(f"镜头片段范围无效：{clip.get('name', asset.name)}")
                if clip.get("track") == "video" and asset.media_type == "audio":
                    raise RuntimeError(f"音频素材不能作为视频镜头：{asset.name}")
                is_visual_layer = str(clip.get("role") or "").endswith("_visual")
                if is_visual_layer and asset.media_type == "audio":
                    raise RuntimeError(f"音频素材不能作为共享视觉层：{asset.name}")
                if asset.media_type == "image":
                    clip["generated_media_type"] = "image"
                    clip["source_start"] = 0
                asset_duration = asset.duration_ms / 1000
                if (
                    clip.get("track") == "video"
                    and asset.media_type != "image"
                    and asset_duration > 0
                    and not clip.get("loop")
                    and not is_visual_layer
                    and source_start + clip_duration > asset_duration + 0.05
                ):
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

            timeline_duration = render_plan.duration
            cursor = 0.0
            for clip in video_clips:
                start = _float(clip.get("start"), 0.0)
                if start < cursor - 0.01:
                    raise RuntimeError("视频轨存在重叠片段；当前导出仅支持单视频轨不重叠排列")
                cursor = start + _float(clip.get("duration"), 0.0)

            rendered_file = os.path.join(temp_dir, "rendered.mp4")
            mixed_file = os.path.join(temp_dir, "mixed.mp4")
            layered_file = os.path.join(temp_dir, "layered.mp4")
            subtitled_file = os.path.join(temp_dir, "subtitled.mp4")
            branded_file = os.path.join(temp_dir, "branded.mp4")

            for stage_index, stage in enumerate(stages):
                await session.execute(
                    update(Job).where(
                        Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                    ).values(
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
                            _render_gap(ffmpeg, gap_file, start - cursor, target_w, target_h, output_fps)
                            segment_files.append(gap_file)
                        base_segment = os.path.join(temp_dir, f"segment_{len(segment_files):04d}_base.mp4")
                        segment_file = os.path.join(temp_dir, f"segment_{len(segment_files):04d}.mp4")
                        _render_video_segment(ffmpeg, ffprobe, clip, base_segment, target_w, target_h)
                        next_clip = video_clips[index + 1] if index + 1 < len(video_clips) else None
                        _apply_outgoing_transition(
                            ffmpeg, ffprobe, base_segment, clip, next_clip, segment_file,
                            temp_dir, target_w, target_h,
                        )
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
                    _apply_visual_layers(
                        ffmpeg, rendered_file, visual_layers, layered_file,
                        target_w, target_h, timeline_duration, output_fps,
                    )

                elif stage_index == 3:
                    _mix_audio_tracks(
                        ffmpeg, ffprobe, layered_file, audio_clips, mixed_file, timeline_duration
                    )

                elif stage_index == 4:
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
                        output_fps,
                    )

                elif stage_index == 5:
                    _apply_export_watermark(
                        ffmpeg,
                        subtitled_file,
                        branded_file,
                        temp_dir,
                        target_w,
                        target_h,
                        timeline_duration,
                        settings.subtitle_font_path,
                        watermark_required,
                        output_fps,
                    )

                elif stage_index == 6:
                    final_file = os.path.join(temp_dir, f"output.{extension}")
                    if format == "mp4":
                        shutil.copy2(branded_file, final_file)
                    elif format == "mov":
                        _run_command(
                            [ffmpeg, "-i", branded_file, "-c", "copy", "-f", "mov", "-y", final_file],
                            "MOV 封装",
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

                    output_asset_id = f"asset-export-{job_id.removeprefix('job-')}"
                    output_asset = await session.get(Asset, output_asset_id)
                    if not output_asset:
                        output_asset = Asset(
                            id=output_asset_id,
                            owner_id=project.owner_id,
                            name=f"{project.name}-{format}-{resolution}",
                            media_type="video",
                            source_type="render_output",
                            status="ready",
                            processing_status="ready",
                            mime_type=content_type,
                            file_path=object_name,
                            preview_path=object_name,
                            file_size_mb=round(os.path.getsize(final_file) / (1024 * 1024), 2),
                            duration_ms=round(timeline_duration * 1000),
                            width=target_w,
                            height=target_h,
                            fps=float(output_fps),
                            has_audio=True,
                            asset_metadata={
                                "export_job_id": job_id,
                                "format": format,
                                "resolution": resolution,
                                "aspect_ratio": export_aspect_ratio,
                            },
                        )
                        session.add(output_asset)
                        await session.flush()
                        session.add(
                            AssetSegment(
                                asset_id=output_asset.id,
                                start_ms=0,
                                end_ms=output_asset.duration_ms,
                                title=output_asset.name,
                            )
                        )
                    existing_link = (
                        await session.execute(
                            select(ProjectAssetLink.id).where(
                                ProjectAssetLink.project_id == project.id,
                                ProjectAssetLink.asset_id == output_asset.id,
                                ProjectAssetLink.role == "render_output",
                            )
                        )
                    ).scalar_one_or_none()
                    if not existing_link:
                        session.add(
                            ProjectAssetLink(
                                project_id=project.id,
                                asset_id=output_asset.id,
                                role="render_output",
                                linked_by=project.owner_id,
                            )
                        )
                    project.master_output_asset_id = output_asset.id
                    project.composition.current_render_asset_id = output_asset.id
                    project.status = "ready"
                    project.script.revision += 1
                    project.composition.revision = project.script.revision
                    await session.flush()
                    await recalculate_storage_usage(session, project.owner_id)
                    await record_revision(
                        session,
                        project,
                        project.owner_id,
                        "export",
                        {"job_id": job_id, "asset_id": output_asset.id},
                    )

                    resolution_label = "4K" if resolution.lower() == "4k" else resolution.upper()
                    export_label = f"{format.upper()} · {export_aspect_ratio} · {resolution_label}"
                    completed = await complete_job_success(
                        session,
                        job_id,
                        values={
                            "progress": 100,
                            "stage": "完成",
                            "detail": f"导出完成：{export_label}",
                            "result": "查看结果",
                            "result_detail": f"导出规格：{export_label}；成片已按唯一项目脚本、镜头和全片设置导出",
                            "result_url": export_url,
                            "result_path": object_name,
                        },
                    )
                    if not completed:
                        await session.rollback()
                        return
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
                                message=f"{project.name} 已完成 {export_label} 导出",
                                link=f"/workspace/projects/{project.id}?exportJob={job_id}",
                            )
                        )
                    await session.commit()

    except Exception as exc:
        async with async_session_factory() as failure_session:
            from sqlalchemy import update

            from app.models.job import Job

            message = str(exc)[:600]
            await failure_session.execute(
                update(Job).where(
                    Job.id == job_id, Job.status.in_(["QUEUED", "RUNNING"])
                ).values(
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
