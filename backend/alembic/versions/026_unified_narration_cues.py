"""将 VoiceLine 升级为字幕与配音共享的统一台词段。

Revision ID: 026_unified_narration_cues
Revises: 025_voice_take_selection_fk
"""

from alembic import op
import sqlalchemy as sa


revision = "026_unified_narration_cues"
down_revision = "025_voice_take_selection_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_lines", sa.Column("source_key", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("voice_lines", sa.Column("end_ms", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("voice_lines", sa.Column("speech_budget_ms", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("voice_lines", sa.Column("caption_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("voice_lines", sa.Column("voice_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("voice_lines", sa.Column("timing_status", sa.String(length=30), nullable=False, server_default="pending"))
    op.execute(
        """
        UPDATE voice_lines
        SET source_key = 'legacy:' || scene_id || ':' || line_index,
            end_ms = start_ms + GREATEST(target_duration_ms, 1),
            speech_budget_ms = GREATEST(target_duration_ms, 1),
            timing_status = CASE
                WHEN status = 'ready' THEN 'fit'
                ELSE 'pending'
            END
        """
    )
    op.create_index("ix_voice_lines_source_key", "voice_lines", ["source_key"])
    op.create_index("ix_voice_lines_timing_status", "voice_lines", ["timing_status"])
    op.alter_column("voice_lines", "source_key", server_default=None)
    op.alter_column("voice_lines", "end_ms", server_default=None)
    op.alter_column("voice_lines", "speech_budget_ms", server_default=None)
    op.alter_column("voice_lines", "caption_enabled", server_default=None)
    op.alter_column("voice_lines", "voice_enabled", server_default=None)
    op.alter_column("voice_lines", "timing_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_voice_lines_timing_status", table_name="voice_lines")
    op.drop_index("ix_voice_lines_source_key", table_name="voice_lines")
    op.drop_column("voice_lines", "timing_status")
    op.drop_column("voice_lines", "voice_enabled")
    op.drop_column("voice_lines", "caption_enabled")
    op.drop_column("voice_lines", "speech_budget_ms")
    op.drop_column("voice_lines", "end_ms")
    op.drop_column("voice_lines", "source_key")
