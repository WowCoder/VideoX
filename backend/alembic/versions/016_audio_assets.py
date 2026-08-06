"""audio asset import metadata

Revision ID: 016_audio_assets
Revises: 015_project_media
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "016_audio_assets"
down_revision: str | None = "015_project_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("media_type", sa.String(length=20), server_default="video", nullable=False),
    )
    op.add_column(
        "assets",
        sa.Column("has_audio", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("assets", sa.Column("preview_path", sa.String(length=500), nullable=True))
    op.add_column("assets", sa.Column("audio_codec", sa.String(length=50), nullable=True))
    op.add_column("assets", sa.Column("sample_rate", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("channels", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("bitrate", sa.Integer(), nullable=True))
    op.create_index("ix_assets_media_type", "assets", ["media_type"])


def downgrade() -> None:
    op.drop_index("ix_assets_media_type", table_name="assets")
    op.drop_column("assets", "bitrate")
    op.drop_column("assets", "channels")
    op.drop_column("assets", "sample_rate")
    op.drop_column("assets", "audio_codec")
    op.drop_column("assets", "preview_path")
    op.drop_column("assets", "has_audio")
    op.drop_column("assets", "media_type")
