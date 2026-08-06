"""project media index and durable export result path

Revision ID: 015_project_media
Revises: 014_backfill_timeline_lineage
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "015_project_media"
down_revision: str | None = "014_backfill_timeline_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _media_id() -> str:
    return f"media-{uuid.uuid4().hex[:12]}"


def _insert_media(bind, values: dict) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO project_media_items (
                id, project_id, kind, dedupe_key, asset_id, storage_path,
                media_type, source_project_id, source_script_id, source_shot_id,
                name, duration, thumbnail_path, created_at
            ) VALUES (
                :id, :project_id, :kind, :dedupe_key, :asset_id, :storage_path,
                :media_type, :source_project_id, :source_script_id, :source_shot_id,
                :name, :duration, :thumbnail_path, now()
            )
            ON CONFLICT (project_id, dedupe_key) DO NOTHING
            """
        ),
        {"id": _media_id(), **values},
    )


def _generated_kind(path: str, media_type: str) -> str:
    if "/effects/" in path:
        return "ai_effect_video"
    return "ai_video" if media_type == "video" else "ai_image"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("result_path", sa.String(length=1000), nullable=True))

    op.create_table(
        "project_media_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("dedupe_key", sa.String(length=1100), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.String(length=1000), nullable=True),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("source_project_id", sa.String(length=64), nullable=True),
        sa.Column("source_script_id", sa.String(length=64), nullable=True),
        sa.Column("source_shot_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("duration", sa.Float(), server_default="0", nullable=False),
        sa.Column("thumbnail_path", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_script_id"], ["scripts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_shot_id"], ["shots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "dedupe_key", name="uq_project_media_project_key"),
    )
    op.create_index("ix_project_media_items_project_id", "project_media_items", ["project_id"])
    op.create_index("ix_project_media_items_kind", "project_media_items", ["kind"])
    op.create_index("ix_project_media_items_asset_id", "project_media_items", ["asset_id"])
    op.create_index("ix_project_media_items_storage_path", "project_media_items", ["storage_path"])
    op.create_index("ix_project_media_items_source_project_id", "project_media_items", ["source_project_id"])
    op.create_index("ix_project_media_items_source_script_id", "project_media_items", ["source_script_id"])
    op.create_index("ix_project_media_items_source_shot_id", "project_media_items", ["source_shot_id"])

    bind = op.get_bind()
    projects = bind.execute(
        sa.text(
            """
            SELECT p.id, p.source_script_id, p.timeline, s.project_id AS source_project_id
            FROM projects p
            LEFT JOIN scripts s ON s.id = p.source_script_id
            WHERE p.source_script_id IS NOT NULL
            """
        )
    ).mappings().all()

    for project in projects:
        for item in list(project["timeline"] or []):
            asset_id = item.get("asset_id")
            if asset_id:
                asset = bind.execute(
                    sa.text("SELECT project_id, name, duration, thumbnail_path FROM assets WHERE id = :id"),
                    {"id": asset_id},
                ).mappings().first()
                if asset:
                    _insert_media(bind, {
                        "project_id": project["id"],
                        "kind": "source_asset",
                        "dedupe_key": f"asset:{asset_id}",
                        "asset_id": asset_id,
                        "storage_path": None,
                        "media_type": "video",
                        "source_project_id": asset["project_id"],
                        "source_script_id": item.get("source_script_id") or project["source_script_id"],
                        "source_shot_id": item.get("source_shot_id"),
                        "name": asset["name"],
                        "duration": float(asset["duration"] or 0),
                        "thumbnail_path": asset["thumbnail_path"],
                    })

            path = item.get("generated_media_path")
            if path:
                media_type = item.get("generated_media_type") or "video"
                _insert_media(bind, {
                    "project_id": project["id"],
                    "kind": _generated_kind(str(path), media_type),
                    "dedupe_key": f"storage:{path}",
                    "asset_id": None,
                    "storage_path": str(path),
                    "media_type": media_type,
                    "source_project_id": project["source_project_id"],
                    "source_script_id": item.get("source_script_id") or project["source_script_id"],
                    "source_shot_id": item.get("source_shot_id"),
                    "name": item.get("name") or "AI 生成媒体",
                    "duration": float(item.get("duration") or 0),
                    "thumbnail_path": str(path) if media_type == "image" else None,
                })

        snapshot_rows = bind.execute(
            sa.text(
                """
                SELECT shot.source_shot_id,
                       shot.description,
                       shot.duration,
                       shot.generated_image_path,
                       shot.generated_video_path,
                       shot.generated_effect_video_path
                FROM shots shot
                JOIN script_units unit ON unit.id = shot.unit_id
                JOIN scripts script ON script.id = unit.script_id
                WHERE script.project_id = :project_id AND script.is_snapshot = true
                """
            ),
            {"project_id": project["id"]},
        ).mappings().all()
        for shot in snapshot_rows:
            generated = (
                (shot["generated_image_path"], "ai_image", "image"),
                (shot["generated_video_path"], "ai_video", "video"),
                (shot["generated_effect_video_path"], "ai_effect_video", "video"),
            )
            for path, kind, media_type in generated:
                if not path:
                    continue
                _insert_media(bind, {
                    "project_id": project["id"],
                    "kind": kind,
                    "dedupe_key": f"storage:{path}",
                    "asset_id": None,
                    "storage_path": path,
                    "media_type": media_type,
                    "source_project_id": project["source_project_id"],
                    "source_script_id": project["source_script_id"],
                    "source_shot_id": shot["source_shot_id"],
                    "name": shot["description"] or "AI 生成媒体",
                    "duration": float(shot["duration"] or 0),
                    "thumbnail_path": path if media_type == "image" else None,
                })

    export_jobs = bind.execute(
        sa.text(
            """
            SELECT id, project_id, payload
            FROM jobs
            WHERE type = '导出' AND status = 'SUCCEEDED'
            """
        )
    ).mappings().all()
    for job in export_jobs:
        payload = job["payload"] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        export_format = payload.get("format", "mp4")
        extension = "mp4" if export_format == "mp4" else "mov"
        result_path = f"exports/{job['project_id']}/{job['id']}.{extension}"
        bind.execute(
            sa.text("UPDATE jobs SET result_path = :path WHERE id = :id"),
            {"path": result_path, "id": job["id"]},
        )


def downgrade() -> None:
    op.drop_index("ix_project_media_items_source_shot_id", table_name="project_media_items")
    op.drop_index("ix_project_media_items_source_script_id", table_name="project_media_items")
    op.drop_index("ix_project_media_items_source_project_id", table_name="project_media_items")
    op.drop_index("ix_project_media_items_storage_path", table_name="project_media_items")
    op.drop_index("ix_project_media_items_asset_id", table_name="project_media_items")
    op.drop_index("ix_project_media_items_kind", table_name="project_media_items")
    op.drop_index("ix_project_media_items_project_id", table_name="project_media_items")
    op.drop_table("project_media_items")
    op.drop_column("jobs", "result_path")
