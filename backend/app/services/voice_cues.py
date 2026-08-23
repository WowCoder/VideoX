"""统一台词段与项目字幕之间的同步。"""

from sqlalchemy import select

from app.models.voice import VoiceLine, VoiceTake
from app.services.tts.normalization import text_hash


async def sync_voice_cues(
    session,
    project,
    plans: list[dict],
    *,
    source_revision: int,
    profile_id: str | None = None,
    instruction: str | None = None,
    emotion: str | None = None,
    scope_scene_ids: set[str] | None = None,
) -> tuple[list[VoiceLine], bool]:
    """将字幕计划写入持久台词段，并保留已有 Take。"""

    scene_ids = scope_scene_ids if scope_scene_ids is not None else {plan["scene_id"] for plan in plans}
    if not scene_ids:
        return [], False
    existing = (
        await session.execute(
            select(VoiceLine).where(
                VoiceLine.project_id == project.id,
                VoiceLine.scene_id.in_(scene_ids),
            )
        )
    ).scalars().unique().all()
    by_source_key = {line.source_key: line for line in existing if line.source_key}
    by_position = {(line.scene_id, line.line_index): line for line in existing}
    desired_ids: set[str] = set()
    result: list[VoiceLine] = []
    master_stale = False

    for plan in plans:
        line = by_source_key.get(plan["source_key"])
        if line is None:
            # source_key 会随镜头边界变化；相同场景序号是旧数据和时间调整后
            # 最稳妥的回退身份，可保留既有 Take。
            line = by_position.get((plan["scene_id"], plan["line_index"]))
        hashed = text_hash(plan["text"])
        if line is None:
            line = VoiceLine(
                project_id=project.id,
                scene_id=plan["scene_id"],
                line_index=plan["line_index"],
                source_key=plan["source_key"],
                text=plan["text"],
                text_hash=hashed,
                status="draft",
                timing_status="pending",
            )
            session.add(line)
            await session.flush()
            master_stale = True
        else:
            content_changed = line.text_hash != hashed
            timing_changed = (
                line.start_ms != plan["start_ms"]
                or line.end_ms != plan["end_ms"]
                or line.speech_budget_ms != plan["speech_budget_ms"]
            )
            if (content_changed or timing_changed) and line.selected_take_id:
                line.status = "stale"
                line.timing_status = "pending"
                master_stale = True

        line.scene_id = plan["scene_id"]
        line.line_index = plan["line_index"]
        line.source_key = plan["source_key"]
        line.text = plan["text"]
        line.text_hash = hashed
        line.text_source = plan["text_source"]
        line.source_revision = source_revision
        line.start_ms = plan["start_ms"]
        line.end_ms = plan["end_ms"]
        line.target_duration_ms = plan["target_duration_ms"]
        line.speech_budget_ms = plan["speech_budget_ms"]
        line.pause_after_ms = plan["pause_after_ms"]
        line.caption_enabled = plan["caption_enabled"]
        line.voice_enabled = plan["voice_enabled"]
        line.start_shot_id = plan["start_shot_id"]
        line.end_shot_id = plan["end_shot_id"]
        if profile_id is not None:
            line.voice_profile_id = profile_id
        if instruction is not None:
            line.instruction = instruction
        if emotion is not None:
            line.emotion = emotion
        desired_ids.add(line.id)
        result.append(line)

    for line in existing:
        if line.id not in desired_ids:
            if line.selected_take_id:
                master_stale = True
            # 不级联删除历史 Take。暂时退出字幕/配音轨，后续字幕再次增加到
            # 这个位置时仍可复用该逻辑台词的历史版本。
            line.caption_enabled = False
            line.voice_enabled = False
            line.status = "stale"
    await session.flush()

    selected_ids = [line.selected_take_id for line in result if line.selected_take_id]
    takes = (
        await session.execute(select(VoiceTake).where(VoiceTake.id.in_(selected_ids)))
    ).scalars().all() if selected_ids else []
    takes_by_id = {take.id: take for take in takes}
    for line in result:
        take = takes_by_id.get(line.selected_take_id or "")
        if not line.voice_enabled:
            continue
        if take and line.status != "stale" and take.duration_ms > line.speech_budget_ms:
            line.timing_status = "conflict"
            line.status = "timing_conflict"
            master_stale = True
        elif take and line.status not in {"stale", "generating", "failed"}:
            line.timing_status = "fit"
            line.status = "ready"
    await session.flush()
    return result, master_stale
