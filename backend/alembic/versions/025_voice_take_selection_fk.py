"""Add the deferred selected VoiceTake foreign key.

Revision ID: 025_voice_take_selection_fk
Revises: 024_ai_voiceover
"""

from collections.abc import Sequence

from alembic import op


revision: str = "025_voice_take_selection_fk"
down_revision: str | None = "024_ai_voiceover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_voice_lines_selected_take",
        "voice_lines",
        "voice_takes",
        ["selected_take_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_voice_lines_selected_take", "voice_lines", type_="foreignkey")
