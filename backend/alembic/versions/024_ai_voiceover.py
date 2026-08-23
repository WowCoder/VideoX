"""Add segment-level AI voiceover models.

Revision ID: 024_ai_voiceover
Revises: 023_reconcile_workspace
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "024_ai_voiceover"
down_revision: str | None = "023_reconcile_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(50), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="dashscope"),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("voice_id", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="system"),
        sa.Column("language", sa.String(30), nullable=False, server_default="Chinese"),
        sa.Column("default_instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_emotion", sa.String(40), nullable=False, server_default=""),
        sa.Column("default_speed", sa.Float(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_profiles_owner_id", "voice_profiles", ["owner_id"])
    op.create_index("ix_voice_profiles_project_id", "voice_profiles", ["project_id"])
    op.create_index("ix_voice_profiles_status", "voice_profiles", ["status"])
    op.create_index("ix_voice_profiles_owner_project", "voice_profiles", ["owner_id", "project_id"])

    op.create_table(
        "voice_lines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("script_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_shot_id", sa.String(64), sa.ForeignKey("shots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("end_shot_id", sa.String(64), sa.ForeignKey("shots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_source", sa.String(20), nullable=False, server_default="narration"),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pause_before_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pause_after_ms", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("voice_profile_id", sa.String(64), sa.ForeignKey("voice_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("emotion", sa.String(40), nullable=False, server_default=""),
        sa.Column("speed_policy", sa.String(30), nullable=False, server_default="timeline_locked"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("selected_take_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "scene_id", "line_index", name="uq_voice_lines_project_scene_index"),
    )
    op.create_index("ix_voice_lines_project_id", "voice_lines", ["project_id"])
    op.create_index("ix_voice_lines_scene_id", "voice_lines", ["scene_id"])
    op.create_index("ix_voice_lines_text_hash", "voice_lines", ["text_hash"])
    op.create_index("ix_voice_lines_status", "voice_lines", ["status"])
    op.create_index("ix_voice_lines_selected_take_id", "voice_lines", ["selected_take_id"])
    op.create_index("ix_voice_lines_project_status", "voice_lines", ["project_id", "status"])

    op.create_table(
        "voice_takes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("voice_line_id", sa.String(64), sa.ForeignKey("voice_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("voice_id", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(160), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billed_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("time_stretch_ratio", sa.Float(), nullable=False, server_default="1"),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("quality_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_takes_voice_line_id", "voice_takes", ["voice_line_id"])
    op.create_index("ix_voice_takes_asset_id", "voice_takes", ["asset_id"])
    op.create_index("ix_voice_takes_job_id", "voice_takes", ["job_id"])
    op.create_index("ix_voice_takes_request_hash", "voice_takes", ["request_hash"])
    op.create_index("ix_voice_takes_status", "voice_takes", ["status"])
    op.create_index("ix_voice_takes_is_selected", "voice_takes", ["is_selected"])
    op.create_index("ix_voice_takes_line_created", "voice_takes", ["voice_line_id", "created_at"])


def downgrade() -> None:
    op.drop_table("voice_takes")
    op.drop_table("voice_lines")
    op.drop_table("voice_profiles")
