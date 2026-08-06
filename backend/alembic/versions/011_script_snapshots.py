"""script snapshots

Revision ID: 011_script_snapshots
Revises: 010_embedding_provenance
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "011_script_snapshots"
down_revision: str | None = "010_embedding_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scripts",
        sa.Column("is_snapshot", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "scripts",
        sa.Column("parent_script_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_scripts_parent_script_id",
        "scripts",
        "scripts",
        ["parent_script_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_scripts_is_snapshot", "scripts", ["is_snapshot"])
    op.create_index("ix_scripts_parent_script_id", "scripts", ["parent_script_id"])
    op.execute(
        """
        UPDATE scripts AS snapshot
        SET is_snapshot = true,
            parent_script_id = projects.source_script_id
        FROM projects
        WHERE snapshot.project_id = projects.id
          AND projects.source_script_id IS NOT NULL
          AND snapshot.title LIKE '%（初剪副本）'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_scripts_parent_script_id", table_name="scripts")
    op.drop_index("ix_scripts_is_snapshot", table_name="scripts")
    op.drop_constraint("fk_scripts_parent_script_id", "scripts", type_="foreignkey")
    op.drop_column("scripts", "parent_script_id")
    op.drop_column("scripts", "is_snapshot")
