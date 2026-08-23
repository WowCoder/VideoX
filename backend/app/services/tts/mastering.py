"""配音音频校验、标准化与项目级母带拼接。"""

import json
import subprocess
from pathlib import Path

from app.config import get_settings


def probe_audio(path: str) -> dict:
    settings = get_settings()
    process = subprocess.run(
        [settings.ffprobe_path, "-v", "error", "-show_entries", "format=duration:stream=codec_type,sample_rate,channels", "-of", "json", path],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(process.stdout)
    audio_stream = next((item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise RuntimeError("语音文件中没有可解码的音轨")
    duration_ms = round(float(payload.get("format", {}).get("duration") or 0) * 1000)
    if duration_ms <= 0:
        raise RuntimeError("语音文件时长无效")
    return {
        "duration_ms": duration_ms,
        "sample_rate": int(audio_stream.get("sample_rate") or 0),
        "channels": int(audio_stream.get("channels") or 0),
    }


def normalize_take(source_path: str, target_path: str, *, target_duration_ms: int = 0) -> dict:
    settings = get_settings()
    source = probe_audio(source_path)
    ratio = 1.0
    filters: list[str] = []
    if target_duration_ms > 0 and source["duration_ms"] > target_duration_ms:
        ratio = source["duration_ms"] / target_duration_ms
        if ratio <= settings.ai_tts_auto_time_stretch_limit:
            filters.append(f"atempo={ratio:.6f}")
        else:
            ratio = 1.0
    filters.extend([
        f"aresample={settings.ai_tts_output_sample_rate}",
        "aformat=sample_fmts=s16:channel_layouts=stereo" if settings.ai_tts_output_channels == 2 else "aformat=sample_fmts=s16:channel_layouts=mono",
    ])
    subprocess.run(
        [settings.ffmpeg_path, "-y", "-v", "error", "-i", source_path, "-vn", "-af", ",".join(filters), "-c:a", "pcm_s16le", target_path],
        check=True,
        capture_output=True,
        timeout=180,
    )
    result = probe_audio(target_path)
    result["time_stretch_ratio"] = ratio
    result["overflow_ms"] = max(0, result["duration_ms"] - target_duration_ms) if target_duration_ms else 0
    return result


def build_master(*, clips: list[tuple[str, int]], duration_ms: int, output_path: str) -> dict:
    if duration_ms <= 0:
        raise RuntimeError("项目时间线时长无效，不能生成旁白母带")
    settings = get_settings()
    layout = "stereo" if settings.ai_tts_output_channels == 2 else "mono"
    command = [settings.ffmpeg_path, "-y", "-v", "error", "-f", "lavfi", "-t", f"{duration_ms / 1000:.3f}", "-i", f"anullsrc=r={settings.ai_tts_output_sample_rate}:cl={layout}"]
    for path, _ in clips:
        command.extend(["-i", path])
    filters: list[str] = []
    inputs = ["[0:a]"]
    for index, (_, start_ms) in enumerate(clips, start=1):
        delay = max(0, start_ms)
        filters.append(f"[{index}:a]asetpts=PTS-STARTPTS,adelay={delay}:all=1[v{index}]")
        inputs.append(f"[v{index}]")
    filters.append(f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=first:normalize=0,alimiter=limit=0.95[out]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-t", f"{duration_ms / 1000:.3f}", "-c:a", "pcm_s16le", output_path])
    subprocess.run(command, check=True, capture_output=True, timeout=max(180, round(duration_ms / 1000) * 3))
    return probe_audio(output_path)


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
