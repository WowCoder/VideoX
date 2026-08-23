"""从字幕时间窗构建统一台词段。

TTS 不再二次切句或按字数估算开始时间。每个计划都对应一个明确的字幕
时间窗，字幕和配音共同使用 ``start_ms`` / ``end_ms``。相邻镜头展示相同
字幕时合并为一个台词段，避免同一句在镜头切换处被重复朗读。
"""

from app.services.tts.normalization import normalize_tts_text


def _speech_budget(duration_ms: int) -> tuple[int, int]:
    """给相邻台词留出自然呼吸间隔，返回（朗读预算，尾部停顿）。"""

    duration_ms = max(1, duration_ms)
    pause_after_ms = min(300, round(duration_ms * 0.05))
    return max(1, duration_ms - pause_after_ms), pause_after_ms


def _plan(
    *,
    scene,
    line_index: int,
    text: str,
    source: str,
    start_ms: int,
    end_ms: int,
    shots: list,
) -> dict:
    duration_ms = max(1, end_ms - start_ms)
    speech_budget_ms, pause_after_ms = _speech_budget(duration_ms)
    first = shots[0] if shots else None
    last = shots[-1] if shots else None
    first_key = first.id if first else "scene"
    last_key = last.id if last else "scene"
    return {
        "source_key": f"{source}:{scene.id}:{first_key}:{last_key}",
        "text": normalize_tts_text(text),
        "text_source": source,
        "start_ms": start_ms,
        "end_ms": end_ms,
        # 保留 target_duration_ms 兼容现有生成链路；它现在明确等于朗读预算，
        # 而不是字幕块本身的总时长。
        "target_duration_ms": speech_budget_ms,
        "speech_budget_ms": speech_budget_ms,
        "pause_after_ms": pause_after_ms,
        "caption_enabled": True,
        "voice_enabled": True,
        "start_shot_id": first.id if first else None,
        "end_shot_id": last.id if last else None,
        "scene_id": scene.id,
        "line_index": line_index,
    }


def build_voice_plans(project, selected_scene_ids: set[str], source: str = "effective_subtitles") -> list[dict]:
    """构建时间锁定的台词段。

    ``narration`` 仅为旧任务重放保留；新 UI 始终使用实际字幕。实际字幕按
    连续且文本相同的镜头合并，每个台词段的起止时间严格来自镜头时间线。
    """

    plans: list[dict] = []
    project_cursor = 0
    for scene in project.script.units:
        scene_duration = sum(max(1, shot.duration_ms) for shot in scene.shots)
        if scene.id not in selected_scene_ids:
            project_cursor += scene_duration
            continue
        if not scene.shots or scene_duration <= 0:
            project_cursor += scene_duration
            continue

        if source == "narration":
            text = normalize_tts_text(scene.narration_text)
            if text:
                plans.append(_plan(
                    scene=scene,
                    line_index=0,
                    text=text,
                    source="narration",
                    start_ms=project_cursor,
                    end_ms=project_cursor + scene_duration,
                    shots=list(scene.shots),
                ))
            project_cursor += scene_duration
            continue

        groups: list[dict] = []
        shot_cursor = project_cursor
        for shot in scene.shots:
            duration_ms = max(1, shot.duration_ms)
            effective = normalize_tts_text(shot.subtitle_text or scene.narration_text)
            if not effective:
                shot_cursor += duration_ms
                continue
            # 只有时间上连续且文字相同的字幕才是同一个 cue。旧逻辑只跳过
            # 重复字幕却没有并入时长，会让配音错误地只占第一个镜头。
            if groups and groups[-1]["text"] == effective and groups[-1]["end_ms"] == shot_cursor:
                groups[-1]["shots"].append(shot)
                groups[-1]["end_ms"] += duration_ms
            else:
                groups.append({
                    "text": effective,
                    "start_ms": shot_cursor,
                    "end_ms": shot_cursor + duration_ms,
                    "shots": [shot],
                })
            shot_cursor += duration_ms
        for line_index, group in enumerate(groups):
            plans.append(_plan(
                scene=scene,
                line_index=line_index,
                text=group["text"],
                source="subtitle",
                start_ms=group["start_ms"],
                end_ms=group["end_ms"],
                shots=group["shots"],
            ))
        project_cursor += scene_duration
    return plans
