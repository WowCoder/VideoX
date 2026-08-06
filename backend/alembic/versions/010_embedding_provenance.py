"""embedding provenance

Revision ID: 010_embedding_provenance
Revises: 009_invoice_applications
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "010_embedding_provenance"
down_revision: str | None = "009_invoice_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("clips", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column(
        "clips",
        sa.Column("embedding_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "clips",
        sa.Column("embedding_status", sa.String(length=20), nullable=False, server_default="missing"),
    )
    op.add_column("clips", sa.Column("embedding_source_hash", sa.String(length=64), nullable=True))
    op.add_column("clips", sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE clips
        SET embedding_model = 'text-embedding-v3',
            embedding_dimensions = 1024,
            embedding_status = 'ready',
            embedding_updated_at = created_at
        WHERE embedding IS NOT NULL
        """
    )
    op.create_index("ix_clips_embedding_model", "clips", ["embedding_model"])
    op.create_index("ix_clips_embedding_status", "clips", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_clips_embedding_status", table_name="clips")
    op.drop_index("ix_clips_embedding_model", table_name="clips")
    op.drop_column("clips", "embedding_updated_at")
    op.drop_column("clips", "embedding_source_hash")
    op.drop_column("clips", "embedding_status")
    op.drop_column("clips", "embedding_version")
    op.drop_column("clips", "embedding_dimensions")
    op.drop_column("clips", "embedding_model")
