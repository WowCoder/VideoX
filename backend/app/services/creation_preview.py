"""Real-model previews used before a project exists.

The module is deliberately stateless: callers supply prompts or already-owned
asset context and receive a validated document fragment that can be reviewed
before project creation.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.ai_provider import generate_text


def _model_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError("文本模型未返回合法 JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("文本模型返回的结果不是 JSON 对象")
    return payload


def _number(value: object, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _allocate_durations(shots: list[dict], target_duration_seconds: int) -> None:
    target_ms = max(15_000, min(300_000, int(target_duration_seconds) * 1000))
    minimum_ms = min(1_000, max(100, target_ms // max(1, len(shots))))
    weights = [max(0.5, _number(shot.pop("duration_seconds", 0), 0)) for shot in shots]
    distributable_ms = max(0, target_ms - minimum_ms * len(shots))
    total_weight = sum(weights) or len(shots)
    assigned_ms = 0
    for index, (shot, weight) in enumerate(zip(shots, weights)):
        if index == len(shots) - 1:
            duration_ms = max(100, target_ms - assigned_ms)
        else:
            duration_ms = minimum_ms + round(distributable_ms * weight / total_weight)
            assigned_ms += duration_ms
        shot["duration_ms"] = duration_ms


def normalize_script_preview(raw: str, target_duration_seconds: int) -> dict:
    payload = _model_json(raw)
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list):
        raise RuntimeError("文本模型结果缺少 scenes 数组")
    scenes: list[dict] = []
    all_shots: list[dict] = []
    for raw_scene in raw_scenes[:12]:
        if not isinstance(raw_scene, dict):
            continue
        narration = str(raw_scene.get("narration") or raw_scene.get("narration_text") or "").strip()
        visual = str(raw_scene.get("visual") or raw_scene.get("intent") or "").strip()
        raw_shots = raw_scene.get("shots")
        if not narration or not isinstance(raw_shots, list):
            continue
        shots: list[dict] = []
        for raw_shot in raw_shots[:8]:
            if not isinstance(raw_shot, dict):
                continue
            description = str(raw_shot.get("description") or "").strip()
            if not description:
                continue
            shot = {
                "description": description[:5000],
                "duration_seconds": max(0.5, _number(raw_shot.get("duration_seconds"), 4)),
            }
            shots.append(shot)
            all_shots.append(shot)
        if not shots:
            continue
        scenes.append({
            "title": str(raw_scene.get("title") or raw_scene.get("outline") or f"场景 {len(scenes) + 1}").strip()[:200],
            "narration": narration[:10000],
            "visual": visual[:10000],
            "shots": shots,
        })
    if not scenes or not all_shots:
        raise RuntimeError("文本模型没有生成可用的脚本和分镜")
    _allocate_durations(all_shots, target_duration_seconds)
    for scene in scenes:
        scene["duration_ms"] = sum(shot["duration_ms"] for shot in scene["shots"])
    return {
        "title": str(payload.get("title") or "AI 生成脚本").strip()[:200],
        "summary": str(payload.get("summary") or "").strip()[:2000],
        "scenes": scenes,
    }


async def generate_script_preview(prompt: str, target_duration_seconds: int, tone: str) -> dict:
    raw = await generate_text(
        prompt=f"""请为尚未创建的视频项目生成一版可供用户确认的完整脚本与分镜。
创作目标：{prompt}
表达语气：{tone}
目标总时长：{target_duration_seconds} 秒

只返回合法 JSON：
{{"title":"片名","summary":"叙事策略摘要","scenes":[{{"title":"场景标题","narration":"可直接配音的完整旁白，不要写创作建议","visual":"这一场景的视觉目标","shots":[{{"description":"具体主体、环境、景别、机位、动作、构图、光线和运镜","duration_seconds":4}}]}}]}}

要求：
1. 旁白必须是观众最终会听到的成稿，不得出现“应该、建议、突出、交代”等创作指导语。
2. 每个场景生成 1—4 个可以独立剪辑的具体镜头，禁止使用“围绕本段组合镜头”等占位描述。
3. 建立清晰的开场、发展、转折/证明和收束，避免所有题材套用相同句式。
4. 不捏造用户没有提供的品牌、数字、人物身份或产品事实。
5. 总镜头时长接近 {target_duration_seconds} 秒。""",
        system_prompt="你是专业纪录片和品牌视频编导，只输出合法 JSON，不输出 Markdown。",
        temperature=0.65,
        max_tokens=7000,
    )
    return normalize_script_preview(raw, target_duration_seconds)


def normalize_asset_preview(raw: str, available_segments: dict[str, dict]) -> dict:
    payload = _model_json(raw)
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list):
        raise RuntimeError("编排模型结果缺少 scenes 数组")
    scenes: list[dict] = []
    used_segment_ids: set[str] = set()
    for raw_scene in raw_scenes[:30]:
        if not isinstance(raw_scene, dict):
            continue
        raw_shots = raw_scene.get("shots")
        if not isinstance(raw_shots, list):
            continue
        shots: list[dict] = []
        for raw_shot in raw_shots[:8]:
            if not isinstance(raw_shot, dict):
                continue
            segment_id = str(raw_shot.get("segment_id") or "").strip()
            source = available_segments.get(segment_id)
            if not source:
                raise RuntimeError(f"编排模型引用了不可用的素材片段：{segment_id or '空 ID'}")
            if segment_id in used_segment_ids:
                raise RuntimeError(f"编排模型重复使用了素材片段：{segment_id}")
            start_ms = int(source["start_ms"])
            end_ms = int(source["end_ms"])
            available_ms = max(0, end_ms - start_ms)
            requested_ms = round(max(0.5, _number(raw_shot.get("duration_seconds"), 5)) * 1000)
            duration_ms = min(requested_ms, available_ms) if available_ms else 5_000
            description = str(raw_shot.get("description") or source.get("summary") or source.get("title") or "").strip()
            if not description:
                continue
            shots.append({
                "description": description[:5000],
                "duration_ms": max(500, duration_ms),
                "asset_id": source["asset_id"],
                # Request-only whole-asset references deliberately become
                # null here; only real persisted segment IDs may enter a
                # workspace document.
                "segment_id": source.get("segment_id", segment_id),
                "source_start_ms": start_ms,
                "source_end_ms": start_ms + max(500, duration_ms),
            })
            used_segment_ids.add(segment_id)
        narration = str(raw_scene.get("narration") or "").strip()
        if not shots or not narration:
            continue
        scenes.append({
            "title": str(raw_scene.get("title") or f"段落 {len(scenes) + 1}").strip()[:200],
            "narration": narration[:10000],
            "visual": str(raw_scene.get("visual") or shots[0]["description"]).strip()[:10000],
            "duration_ms": sum(shot["duration_ms"] for shot in shots),
            "shots": shots,
        })
    if not scenes:
        raise RuntimeError("编排模型没有引用任何可用素材片段")
    return {
        "title": str(payload.get("title") or "素材分析影片").strip()[:200],
        "summary": str(payload.get("summary") or "").strip()[:2000],
        "scenes": scenes,
    }


async def generate_asset_preview(
    asset_context: list[dict[str, Any]],
    available_segments: dict[str, dict],
    brief: str = "",
) -> dict:
    raw = await generate_text(
        prompt=f"""请从以下用户已选择的真实素材片段中编排一支可编辑影片。
用户补充目标：{brief or '未指定，请从素材本身提炼最清晰的叙事主线'}
素材片段：{json.dumps(asset_context, ensure_ascii=False)}

只返回合法 JSON：
{{"title":"影片标题","summary":"叙事主线与选材说明","scenes":[{{"title":"段落标题","narration":"可直接配音的旁白","visual":"段落视觉目标","shots":[{{"segment_id":"必须原样引用输入中的片段 ID","description":"这个片段在叙事中的具体画面用途","duration_seconds":5}}]}}]}}

要求：
1. 只能引用输入中 eligible_as_visual=true 的 segment_id；音频仅可作为旁白事实和叙事线索，不得作为视觉镜头。
2. 优先选择质量高、内容明确且能形成开场—发展—证明—收束的片段；允许不用完所有素材。
3. 同一片段最多使用一次，避免内容重复。
4. 旁白必须是最终成稿，不得写成剪辑建议。
5. 镜头顺序应由叙事决定，不要机械沿用文件或选择顺序。""",
        system_prompt="你是专业视频剪辑师和纪录片编导，只输出合法 JSON，不输出 Markdown。",
        temperature=0.45,
        max_tokens=8000,
    )
    return normalize_asset_preview(raw, available_segments)
