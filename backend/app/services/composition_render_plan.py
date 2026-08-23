"""Compile the canonical project document into deterministic renderer inputs.

Scene/Shot remains the narrative authority.  The returned dictionaries are an
ephemeral render plan only; they are never persisted as another editable
timeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _reference(value: Any) -> dict | None:
    value = _record(value)
    asset_id = value.get("assetId") or value.get("asset_id")
    if not asset_id:
        return None
    return {**value, "asset_id": str(asset_id)}


def _references(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for raw in value if (item := _reference(raw)) is not None]


def _scope_layers(value: Any) -> dict:
    source = _record(value)
    return {
        "background_music": _reference(source.get("backgroundMusic") or source.get("background_music")),
        "sound_effects": _references(source.get("soundEffects") or source.get("sound_effects")),
        "visual_assets": _references(source.get("visualAssets") or source.get("visual_assets")),
    }


def _transition(value: Any) -> dict:
    source = _record(value)
    transition_type = str(source.get("type") or "cut")
    aliases = {
        "none": "cut",
        "fade_black": "fade",
        "fade_white": "fade",
    }
    duration_ms = source.get("durationMs", source.get("duration_ms"))
    duration = (
        _number(duration_ms, 500.0) / 1000.0
        if duration_ms is not None
        else _number(source.get("duration"), 0.5)
    )
    return {
        **source,
        "type": aliases.get(transition_type, transition_type),
        "duration": max(0.1, min(3.0, duration)),
    }


def _audio_settings(value: Any, default_original_volume: float) -> dict:
    source = _record(value)
    volume = source.get("originalVolume", source.get("original_volume", source.get("volume")))
    return {
        **source,
        "volume": max(0.0, min(200.0, _number(volume, default_original_volume))),
        "muted": bool(source.get("muted", False)),
    }


def _subtitle_settings(value: Any) -> dict:
    source = _record(value)
    position = str(source.get("position") or "bottom")
    if position not in {"top", "center", "bottom"}:
        position = "bottom"
    return {
        **source,
        "position": position,
        "font_size": max(10, min(96, round(_number(source.get("fontSize", source.get("font_size")), 16)))),
        "color": str(source.get("color") or "#ffffff"),
        "align": str(source.get("align") or "center"),
    }


def _effective_adjust(value: Any, visual_settings: Any) -> dict:
    """Resolve project color grading with an optional per-shot override.

    Existing projects used any non-empty shot ``adjust`` object as an override.
    New projects can explicitly store ``mode=inherit`` or ``mode=override``.
    """
    local = _record(value)
    global_grade = _record(_record(visual_settings).get("colorGrade"))
    local_values = {key: item for key, item in local.items() if key != "mode"}
    mode = str(local.get("mode") or ("override" if local_values else "inherit"))
    if mode != "override":
        return dict(global_grade)
    # “当前镜头覆盖”是整套调色的覆盖，不是隐式字段级混合。
    # 这与前端实时预览保持一致，避免导出时又意外继承全片参数。
    return local_values


@dataclass
class CompositionRenderPlan:
    duration: float
    aspect_ratio: str
    fps: int
    video_clips: list[dict] = field(default_factory=list)
    audio_clips: list[dict] = field(default_factory=list)
    subtitle_entries: list[dict] = field(default_factory=list)
    visual_layers: list[dict] = field(default_factory=list)


def _selected_asset_id(shot: Any) -> str | None:
    selected_id = getattr(shot, "selected_media_version_id", None)
    versions = list(getattr(shot, "media_versions", []) or [])
    selected = next((item for item in versions if item.id == selected_id), None)
    if selected is None:
        selected = next((item for item in versions if item.is_selected), None)
    return str(selected.asset_id) if selected else getattr(shot, "asset_id", None)


def _append_audio_clip(
    target: list[dict],
    *,
    role: str,
    reference: dict,
    start: float,
    duration: float,
    fallback_volume: float,
    muted: bool = False,
    ducked: bool = False,
) -> None:
    if duration <= 0:
        return
    volume = _number(reference.get("volume"), fallback_volume)
    if ducked:
        volume *= 0.52
    target.append({
        "id": str(reference.get("id") or f"{role}-{reference['asset_id']}-{start:.3f}"),
        "track": "audio",
        "role": role,
        "start": max(0.0, start),
        "duration": max(0.04, duration),
        "name": str(reference.get("name") or role),
        "asset_id": reference["asset_id"],
        "source_start": max(0.0, _number(reference.get("sourceStartMs", reference.get("source_start_ms"))) / 1000.0),
        "loop": bool(reference.get("loop", role in {"voice", "music"})),
        "audio": {
            "volume": max(0.0, min(200.0, volume)),
            "muted": muted or reference.get("enabled") is False,
            "denoise": bool(reference.get("denoise", False)),
            "fade_in": max(0.0, _number(reference.get("fadeInMs", reference.get("fade_in_ms"))) / 1000.0),
            "fade_out": max(0.0, _number(reference.get("fadeOutMs", reference.get("fade_out_ms"))) / 1000.0),
            "ducked": ducked,
        },
    })


def _same_music(left: dict | None, right: dict | None) -> bool:
    if left is None or right is None:
        return left is right
    fields = ("asset_id", "volume", "loop", "enabled")
    return all(left.get(key) == right.get(key) for key in fields)


def compile_composition_render_plan(project: Any) -> CompositionRenderPlan:
    composition = project.composition
    visual_settings = _record(getattr(composition, "visual_settings", {}))
    global_audio = _record(composition.global_audio)
    raw_scopes = _record(composition.global_scopes)
    film_scope = _scope_layers(raw_scopes.get("film"))
    scene_scopes = _record(raw_scopes.get("scenes"))
    default_original_volume = _number(global_audio.get("originalVolume", global_audio.get("original_volume")), 30.0)
    default_music_volume = _number(global_audio.get("musicVolume", global_audio.get("music_volume")), 24.0)
    voice_volume = _number(global_audio.get("voiceVolume", global_audio.get("voice_volume")), 100.0)
    voice_asset_id = global_audio.get("voiceAssetId") or global_audio.get("voice_asset_id")
    music_asset_id = global_audio.get("musicAssetId") or global_audio.get("music_asset_id")
    voice_enabled = bool(voice_asset_id) and not bool(global_audio.get("voiceMuted", global_audio.get("voice_muted", False)))
    ducking = global_audio.get("duckingEnabled", global_audio.get("ducking_enabled", True)) is not False

    plan = CompositionRenderPlan(
        duration=0.0,
        aspect_ratio=str(composition.aspect_ratio or "16:9"),
        fps=max(1, min(120, int(composition.fps or 25))),
    )
    shot_ranges: list[dict] = []
    cursor = 0.0
    for scene in sorted(project.script.units, key=lambda item: item.index):
        scene_start = cursor
        scene_scope = _scope_layers(scene_scopes.get(scene.id))
        for shot in sorted(scene.shots, key=lambda item: item.index):
            duration = max(0.04, _number(shot.duration_ms, 8000.0) / 1000.0)
            asset_id = _selected_asset_id(shot)
            if not asset_id:
                raise RuntimeError(f"镜头「{shot.description or shot.id}」尚未选择素材")
            shot_audio = _record(shot.audio_settings)
            shot_music = _reference(shot_audio.get("backgroundMusic") or shot_audio.get("background_music"))
            effective_music = shot_music or scene_scope["background_music"] or film_scope["background_music"]
            if effective_music is None and music_asset_id:
                effective_music = {"asset_id": str(music_asset_id), "volume": default_music_volume, "loop": True}
            clip = {
                "id": shot.id,
                "scene_id": scene.id,
                "track": "video",
                "start": cursor,
                "duration": duration,
                "name": shot.description or scene.outline or "镜头",
                "asset_id": asset_id,
                "source_start": max(0.0, _number(shot.source_start_ms) / 1000.0),
                "source_end": max(0.0, _number(shot.source_end_ms) / 1000.0),
                "transform": _record(shot.transform),
                "adjust": _effective_adjust(shot.adjust, visual_settings),
                "motion": _record(shot.motion),
                "audio": _audio_settings(shot.audio_settings, default_original_volume),
                "transition": _transition(shot.transition),
                "fps": plan.fps,
            }
            plan.video_clips.append(clip)
            if str(shot.subtitle_text or "").strip():
                plan.subtitle_entries.append({
                    "text": shot.subtitle_text,
                    "start": cursor,
                    "duration": duration,
                    "settings": _subtitle_settings(shot.subtitle_settings),
                })
            shot_ranges.append({
                "shot": shot,
                "scene_id": scene.id,
                "start": cursor,
                "duration": duration,
                "music": effective_music,
                "scene_scope": scene_scope,
            })
            for effect in _references(shot_audio.get("soundEffects") or shot_audio.get("sound_effects")):
                at = max(0.0, _number(effect.get("atMs", effect.get("at_ms"))) / 1000.0)
                _append_audio_clip(
                    plan.audio_clips,
                    role="shot_sfx",
                    reference=effect,
                    start=cursor + at,
                    duration=min(duration - at, _number(effect.get("durationMs"), duration * 1000.0) / 1000.0),
                    fallback_volume=72.0,
                )
            cursor += duration
        scene_duration = cursor - scene_start
        for effect in scene_scope["sound_effects"]:
            at = max(0.0, _number(effect.get("atMs", effect.get("at_ms"))) / 1000.0)
            _append_audio_clip(
                plan.audio_clips,
                role="scene_sfx",
                reference=effect,
                start=scene_start + at,
                duration=min(scene_duration - at, _number(effect.get("durationMs"), scene_duration * 1000.0) / 1000.0),
                fallback_volume=72.0,
            )
        for visual in scene_scope["visual_assets"]:
            plan.visual_layers.append({
                **visual,
                "role": "scene_visual",
                "start": scene_start,
                "duration": scene_duration,
            })

    plan.duration = cursor
    if voice_asset_id:
        _append_audio_clip(
            plan.audio_clips,
            role="voice",
            reference={"asset_id": str(voice_asset_id), "loop": False},
            start=0.0,
            duration=plan.duration,
            fallback_volume=voice_volume,
            muted=not voice_enabled,
        )

    # Merge adjacent ranges with the same effective music so film/project music
    # continues across shot boundaries instead of restarting every shot.
    music_ranges: list[dict] = []
    for item in shot_ranges:
        music = item["music"]
        if music is None:
            continue
        if music_ranges and _same_music(music_ranges[-1]["reference"], music) and abs(
            music_ranges[-1]["start"] + music_ranges[-1]["duration"] - item["start"]
        ) < 0.001:
            music_ranges[-1]["duration"] += item["duration"]
        else:
            music_ranges.append({"reference": music, "start": item["start"], "duration": item["duration"]})
    for item in music_ranges:
        _append_audio_clip(
            plan.audio_clips,
            role="music",
            reference=item["reference"],
            start=item["start"],
            duration=item["duration"],
            fallback_volume=default_music_volume,
            muted=bool(global_audio.get("musicMuted", global_audio.get("music_muted", False))),
            ducked=ducking and voice_enabled,
        )

    for effect in film_scope["sound_effects"]:
        at = max(0.0, _number(effect.get("atMs", effect.get("at_ms"))) / 1000.0)
        _append_audio_clip(
            plan.audio_clips,
            role="film_sfx",
            reference=effect,
            start=at,
            duration=min(plan.duration - at, _number(effect.get("durationMs"), plan.duration * 1000.0) / 1000.0),
            fallback_volume=72.0,
        )
    for visual in film_scope["visual_assets"]:
        plan.visual_layers.append({**visual, "role": "film_visual", "start": 0.0, "duration": plan.duration})
    for raw in _record(composition.visual_layers).get("items", []):
        visual = _reference(raw)
        if visual is None or visual.get("enabled") is False:
            continue
        start = max(0.0, _number(raw.get("startMs", raw.get("start_ms"))) / 1000.0)
        if start >= plan.duration:
            continue
        duration = _number(raw.get("durationMs", raw.get("duration_ms")), plan.duration * 1000.0) / 1000.0
        plan.visual_layers.append({
            **visual,
            "role": "timeline_visual",
            "start": start,
            "duration": max(0.04, min(plan.duration - start, duration)),
        })
    return plan
