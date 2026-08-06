"""separate sketch effect video output

Revision ID: 012_effect_video_path
Revises: 011_script_snapshots
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "012_effect_video_path"
down_revision: str | None = "011_script_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shots",
        sa.Column("generated_effect_video_path", sa.String(length=500), nullable=True),
    )
    op.execute(
        """
        UPDATE shots
        SET generated_effect_video_path = generated_video_path,
            generated_video_path = NULL
        WHERE generated_video_path LIKE '%/effects/%'
        """
    )


def downgrade() -> None:
    op.drop_column("shots", "generated_effect_video_path")
