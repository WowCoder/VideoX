"""backfill timeline lineage for existing rough cuts

Revision ID: 014_backfill_timeline_lineage
Revises: 013_script_timeline_lineage
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "014_backfill_timeline_lineage"
down_revision: str | None = "013_script_timeline_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LINEAGE_KEYS = {
    "source_script_id",
    "source_unit_id",
    "source_shot_id",
    "snapshot_script_id",
    "snapshot_unit_id",
    "snapshot_shot_id",
    "origin",
    "sync_status",
}


def upgrade() -> None:
    bind = op.get_bind()
    projects = bind.execute(
        sa.text(
            """
            SELECT id, source_script_id, timeline
            FROM projects
            WHERE source_script_id IS NOT NULL
              AND timeline IS NOT NULL
            """
        )
    ).mappings().all()

    for project in projects:
        timeline = list(project["timeline"] or [])
        if not timeline:
            continue
        snapshot_script_id = bind.execute(
            sa.text(
                """
                SELECT id
                FROM scripts
                WHERE project_id = :project_id
                  AND is_snapshot = true
                  AND parent_script_id = :source_script_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"project_id": project["id"], "source_script_id": project["source_script_id"]},
        ).scalar_one_or_none()
        if not snapshot_script_id:
            continue

        units = bind.execute(
            sa.text(
                """
                SELECT id, source_unit_id, index, text
                FROM script_units
                WHERE script_id = :script_id
                ORDER BY index, id
                """
            ),
            {"script_id": snapshot_script_id},
        ).mappings().all()
        shots = bind.execute(
            sa.text(
                """
                SELECT shot.id,
                       shot.source_shot_id,
                       shot.selected_clip_id,
                       unit.id AS snapshot_unit_id,
                       unit.source_unit_id,
                       unit.index AS unit_index,
                       shot.index AS shot_index
                FROM shots AS shot
                JOIN script_units AS unit ON unit.id = shot.unit_id
                WHERE unit.script_id = :script_id
                ORDER BY unit.index, shot.index, shot.id
                """
            ),
            {"script_id": snapshot_script_id},
        ).mappings().all()

        shots_by_clip: dict[str, list[dict]] = defaultdict(list)
        for shot in shots:
            if shot["selected_clip_id"]:
                shots_by_clip[str(shot["selected_clip_id"])].append(dict(shot))
        unused_units = [dict(unit) for unit in units]
        changed = False

        for item in timeline:
            if item.get("source_script_id"):
                continue
            if item.get("track") == "video" and item.get("source_clip_id"):
                candidates = shots_by_clip.get(str(item["source_clip_id"]), [])
                if not candidates:
                    continue
                shot = candidates.pop(0)
                item.update(
                    {
                        "source_script_id": project["source_script_id"],
                        "source_unit_id": shot["source_unit_id"],
                        "source_shot_id": shot["source_shot_id"],
                        "snapshot_script_id": snapshot_script_id,
                        "snapshot_unit_id": shot["snapshot_unit_id"],
                        "snapshot_shot_id": shot["id"],
                        "origin": "script_match",
                        "sync_status": "synced",
                    }
                )
                changed = True
            elif item.get("track") == "subtitle" and unused_units:
                matching_index = next(
                    (
                        index
                        for index, unit in enumerate(unused_units)
                        if unit.get("text") and unit.get("text") == item.get("text")
                    ),
                    0,
                )
                unit = unused_units.pop(matching_index)
                item.update(
                    {
                        "source_script_id": project["source_script_id"],
                        "source_unit_id": unit["source_unit_id"],
                        "source_shot_id": None,
                        "snapshot_script_id": snapshot_script_id,
                        "snapshot_unit_id": unit["id"],
                        "snapshot_shot_id": None,
                        "origin": "script_subtitle",
                        "sync_status": "synced",
                    }
                )
                changed = True

        if changed:
            bind.execute(
                sa.text("UPDATE projects SET timeline = CAST(:timeline AS json) WHERE id = :project_id"),
                {"timeline": json.dumps(timeline, ensure_ascii=False), "project_id": project["id"]},
            )


def downgrade() -> None:
    bind = op.get_bind()
    projects = bind.execute(
        sa.text("SELECT id, timeline FROM projects WHERE source_script_id IS NOT NULL")
    ).mappings().all()
    for project in projects:
        timeline = list(project["timeline"] or [])
        changed = False
        for item in timeline:
            for key in LINEAGE_KEYS:
                if key in item:
                    item.pop(key, None)
                    changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE projects SET timeline = CAST(:timeline AS json) WHERE id = :project_id"),
                {"timeline": json.dumps(timeline, ensure_ascii=False), "project_id": project["id"]},
            )
