"""持久化项目时间线与导出结果地址。

Revision ID: 002_project_timeline
Revises: 001_initial
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_project_timeline"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("timeline", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("projects", sa.Column("timeline_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("projects", sa.Column("timeline_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("thumbnail_path", sa.String(length=500), nullable=True))
    op.add_column("jobs", sa.Column("result_url", sa.String(length=1000), nullable=True))
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=50), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("membership_id", sa.String(length=50), sa.ForeignKey("memberships.id"), nullable=False),
        sa.Column("membership_name", sa.String(length=100), nullable=False),
        sa.Column("billing_cycle", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False, index=True),
        sa.Column("pay_url", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_column("jobs", "result_url")
    op.drop_column("assets", "thumbnail_path")
    op.drop_column("projects", "timeline_updated_at")
    op.drop_column("projects", "timeline_version")
    op.drop_column("projects", "timeline")
