"""用户活跃统计与运营后台系统资源快照。

Revision ID: 032_admin_activity_metrics
Revises: 031_admin_mvp_operations
"""

from alembic import op
import sqlalchemy as sa


revision = "032_admin_activity_metrics"
down_revision = "031_admin_mvp_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_daily_activities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "activity_date", name="uq_user_daily_activity_user_date"),
    )
    op.create_index("ix_user_daily_activities_user_id", "user_daily_activities", ["user_id"])
    op.create_index("ix_user_daily_activities_activity_date", "user_daily_activities", ["activity_date"])
    op.create_index(
        "ix_user_daily_activities_date_user", "user_daily_activities", ["activity_date", "user_id"]
    )

    # 仅回填能够由历史登录时间证明的活跃事件，不推测未记录的历史使用行为。
    op.execute(
        """
        INSERT INTO user_daily_activities (
            id, user_id, activity_date, first_seen_at, last_seen_at, created_at, updated_at
        )
        SELECT
            'activity-' || substr(md5(user_id || activity_date::text), 1, 16),
            user_id,
            activity_date,
            min(last_login_at),
            max(last_login_at),
            now(),
            now()
        FROM (
            SELECT
                user_id,
                (last_login_at AT TIME ZONE 'Asia/Shanghai')::date AS activity_date,
                last_login_at
            FROM user_identities
            WHERE last_login_at IS NOT NULL
        ) known_login_activity
        GROUP BY user_id, activity_date
        ON CONFLICT (user_id, activity_date) DO NOTHING
        """
    )

    op.create_table(
        "system_metric_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("node_name", sa.String(length=100), nullable=False),
        sa.Column("metric_scope", sa.String(length=30), nullable=False),
        sa.Column("collection_source", sa.String(length=20), nullable=False),
        sa.Column("collection_status", sa.String(length=20), nullable=False),
        sa.Column("load_1m", sa.Float(), nullable=True),
        sa.Column("load_5m", sa.Float(), nullable=True),
        sa.Column("load_15m", sa.Float(), nullable=True),
        sa.Column("cpu_count", sa.Integer(), nullable=True),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_percent", sa.Float(), nullable=True),
        sa.Column("uptime_seconds", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_metric_snapshots_node_name", "system_metric_snapshots", ["node_name"])
    op.create_index("ix_system_metric_snapshots_collected_at", "system_metric_snapshots", ["collected_at"])
    op.create_index(
        "ix_system_metric_node_collected", "system_metric_snapshots", ["node_name", "collected_at"]
    )
    op.create_index(
        "ix_system_metric_status_collected",
        "system_metric_snapshots",
        ["collection_status", "collected_at"],
    )


def downgrade() -> None:
    op.drop_table("system_metric_snapshots")
    op.drop_table("user_daily_activities")
