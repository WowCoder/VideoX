"""区分全网选题发现与定点来源监控。

Revision ID: 029_inspiration_discovery
Revises: 028_reconcile_schema_drift
"""

from alembic import op
import sqlalchemy as sa


revision = "029_inspiration_discovery"
down_revision = "028_reconcile_schema_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspiration_tasks",
        sa.Column(
            "discovery_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(
                "json_build_object('source_strategy', 'preferred', 'monitor_brief', '', 'search_recency_days', 7)"
            ),
        ),
    )
    op.add_column("inspiration_sources", sa.Column("last_status", sa.String(length=30), nullable=True))
    op.add_column(
        "inspiration_sources",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("inspiration_runs", sa.Column("outcome", sa.String(length=30), nullable=True))
    op.add_column(
        "inspiration_runs",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_inspiration_runs_outcome", "inspiration_runs", ["outcome"])


def downgrade() -> None:
    op.drop_index("ix_inspiration_runs_outcome", table_name="inspiration_runs")
    op.drop_column("inspiration_runs", "metrics")
    op.drop_column("inspiration_runs", "outcome")
    op.drop_column("inspiration_sources", "consecutive_failures")
    op.drop_column("inspiration_sources", "last_status")
    op.drop_column("inspiration_tasks", "discovery_config")
