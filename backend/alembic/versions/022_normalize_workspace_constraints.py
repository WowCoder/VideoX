"""Normalize inherited workspace columns to the 021 domain model.

Revision ID: 022_normalize_workspace
Revises: 021_project_workspace
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "022_normalize_workspace"
down_revision: str | None = "021_project_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fill_and_require(table: str, column: str, sql_value: str) -> None:
    op.execute(f'UPDATE "{table}" SET "{column}" = {sql_value} WHERE "{column}" IS NULL')
    op.alter_column(table, column, nullable=False)


def _replace_fk(
    table: str,
    old_names: tuple[str, ...],
    new_name: str,
    local_column: str,
    remote_table: str,
    remote_column: str = "id",
    ondelete: str | None = None,
) -> None:
    for name in old_names:
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')
    op.create_foreign_key(
        new_name,
        table,
        remote_table,
        [local_column],
        [remote_column],
        ondelete=ondelete,
    )


def upgrade() -> None:
    # Global assets and their searchable segments.
    for column, value in (
        ("status", "'processing'"),
        ("file_size_mb", "0"),
        ("tags", "'[]'::json"),
        ("uploaded_at", "now()"),
        ("created_at", "now()"),
    ):
        _fill_and_require("assets", column, value)
    op.alter_column("assets", "status", type_=sa.String(30), existing_type=sa.String(50))
    for column in ("file_path", "preview_path", "thumbnail_path"):
        op.alter_column(
            "assets", column, type_=sa.String(1000), existing_type=sa.String(500)
        )
    op.create_index("ix_assets_created_at", "assets", ["created_at"])
    op.create_index("ix_assets_status", "assets", ["status"])

    for column, value in (
        ("title", "''"),
        ("transcript", "''"),
        ("ocr_text", "''"),
        ("quality_score", "0"),
        ("created_at", "now()"),
    ):
        _fill_and_require("asset_segments", column, value)
    op.alter_column(
        "asset_segments", "thumbnail_path", type_=sa.String(1000), existing_type=sa.String(500)
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_clips_embedding_model RENAME TO ix_asset_segments_embedding_model"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_clips_embedding_status RENAME TO ix_asset_segments_embedding_status"
    )
    _replace_fk(
        "asset_segments",
        ("clips_asset_id_fkey", "asset_segments_asset_id_fkey"),
        "fk_asset_segments_asset",
        "asset_id",
        "assets",
        ondelete="CASCADE",
    )

    # Canonical script document rows are now strict, cascading children.
    for column, value in (
        ("title", "''"),
        ("source", "''"),
        ("score", "0"),
        ("reason", "''"),
        ("low_confidence", "false"),
        ("created_at", "now()"),
    ):
        _fill_and_require("candidates", column, value)
    _replace_fk(
        "candidates",
        ("candidates_shot_id_fkey",),
        "fk_candidates_shot",
        "shot_id",
        "shots",
        ondelete="CASCADE",
    )
    _replace_fk(
        "candidates",
        ("candidates_clip_id_fkey", "candidates_segment_id_fkey"),
        "fk_candidates_segment",
        "segment_id",
        "asset_segments",
        ondelete="CASCADE",
    )

    for column, value in (
        ("initial", "'P'"),
        ("type", "'AI 科技 / 产品讲解'"),
        ("description", "''"),
        ("status", "'draft'"),
        ("variant", "'stage'"),
        ("created_at", "now()"),
        ("updated_at", "now()"),
    ):
        _fill_and_require("projects", column, value)
    op.alter_column("projects", "status", type_=sa.String(30), existing_type=sa.String(50))
    _replace_fk(
        "projects",
        ("projects_owner_id_fkey",),
        "fk_projects_owner",
        "owner_id",
        "users",
        ondelete="CASCADE",
    )

    for column, value in (
        ("summary", "''"),
        ("status", "'editing'"),
        ("source_type", "'blank'"),
        ("visual_config", "'{}'::json"),
        ("created_at", "now()"),
        ("updated_at", "now()"),
    ):
        _fill_and_require("scripts", column, value)
    op.alter_column("scripts", "status", type_=sa.String(30), existing_type=sa.String(50))
    op.create_index("ix_scripts_status", "scripts", ["status"])
    _replace_fk(
        "scripts",
        ("scripts_project_id_fkey",),
        "fk_scripts_project",
        "project_id",
        "projects",
        ondelete="CASCADE",
    )

    for column, value in (
        ("index", "0"),
        ("outline", "''"),
        ("narration_text", "''"),
        ("intent", "''"),
        ("status", "'editing'"),
        ("notes", "''"),
        ("created_at", "now()"),
    ):
        _fill_and_require("script_units", column, value)
    op.alter_column(
        "script_units", "status", type_=sa.String(30), existing_type=sa.String(50)
    )
    _replace_fk(
        "script_units",
        ("script_units_script_id_fkey",),
        "fk_script_units_script",
        "script_id",
        "scripts",
        ondelete="CASCADE",
    )

    for column, value in (
        ("index", "0"),
        ("description", "''"),
        ("status", "'editing'"),
        ("notes", "''"),
        ("created_at", "now()"),
    ):
        _fill_and_require("shots", column, value)
    op.alter_column("shots", "status", type_=sa.String(30), existing_type=sa.String(50))
    op.create_index("ix_shots_asset_id", "shots", ["asset_id"])
    op.create_index("ix_shots_segment_id", "shots", ["segment_id"])
    _replace_fk(
        "shots",
        ("shots_unit_id_fkey",),
        "fk_shots_unit",
        "unit_id",
        "script_units",
        ondelete="CASCADE",
    )
    _replace_fk(
        "shots",
        ("shots_selected_clip_id_fkey", "shots_segment_id_fkey"),
        "fk_shots_segment",
        "segment_id",
        "asset_segments",
        ondelete="SET NULL",
    )

    # Jobs and account quota rows retain their existing defaults but become non-null as modeled.
    for column, value in (
        ("name", "''"),
        ("type", "''"),
        ("status", "'QUEUED'"),
        ("stage", "''"),
        ("stages", "'[]'::json"),
        ("stage_index", "0"),
        ("progress", "0"),
        ("detail", "''"),
        ("eta", "'预计 1-2 分钟'"),
        ("logs", "'[]'::json"),
        ("result_detail", "''"),
        ("is_simulated", "false"),
        ("created_at", "now()"),
        ("updated_at", "now()"),
    ):
        _fill_and_require("jobs", column, value)

    for column, value in (
        ("rank", "0"),
        ("billing_cycle", "'permanent'"),
        ("processing_minutes", "0"),
        ("ai_image_quota", "0"),
        ("ai_video_quota", "0"),
        ("storage_gb", "0"),
        ("export_quota", "0"),
        ("price", "0"),
    ):
        _fill_and_require("memberships", column, value)

    for column, value in (
        ("avatar_initial", "'U'"),
        ("membership_id", "'membership-free'"),
        ("created_at", "now()"),
        ("updated_at", "now()"),
    ):
        _fill_and_require("users", column, value)


def downgrade() -> None:
    raise RuntimeError(
        "022_normalize_workspace tightens inherited constraints and is intentionally irreversible."
    )
