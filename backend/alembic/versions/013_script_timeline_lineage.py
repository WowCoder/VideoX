"""script and timeline lineage

Revision ID: 013_script_timeline_lineage
Revises: 012_effect_video_path
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "013_script_timeline_lineage"
down_revision: str | None = "012_effect_video_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("script_units", sa.Column("source_unit_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_script_units_source_unit_id",
        "script_units",
        "script_units",
        ["source_unit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_script_units_source_unit_id", "script_units", ["source_unit_id"])

    op.add_column("shots", sa.Column("source_shot_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_shots_source_shot_id",
        "shots",
        "shots",
        ["source_shot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_shots_source_shot_id", "shots", ["source_shot_id"])

    # 为既有脚本快照按稳定 index 补齐来源映射；后续新快照会在创建时直接写入。
    op.execute(
        """
        UPDATE script_units AS snapshot_unit
        SET source_unit_id = source_unit.id
        FROM scripts AS snapshot_script,
             script_units AS source_unit
        WHERE snapshot_unit.script_id = snapshot_script.id
          AND snapshot_script.is_snapshot = true
          AND snapshot_script.parent_script_id IS NOT NULL
          AND source_unit.script_id = snapshot_script.parent_script_id
          AND source_unit.index = snapshot_unit.index
          AND snapshot_unit.source_unit_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE shots AS snapshot_shot
        SET source_shot_id = source_shot.id
        FROM script_units AS snapshot_unit,
             shots AS source_shot
        WHERE snapshot_shot.unit_id = snapshot_unit.id
          AND snapshot_unit.source_unit_id IS NOT NULL
          AND source_shot.unit_id = snapshot_unit.source_unit_id
          AND source_shot.index = snapshot_shot.index
          AND snapshot_shot.source_shot_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_shots_source_shot_id", table_name="shots")
    op.drop_constraint("fk_shots_source_shot_id", "shots", type_="foreignkey")
    op.drop_column("shots", "source_shot_id")
    op.drop_index("ix_script_units_source_unit_id", table_name="script_units")
    op.drop_constraint("fk_script_units_source_unit_id", "script_units", type_="foreignkey")
    op.drop_column("script_units", "source_unit_id")
