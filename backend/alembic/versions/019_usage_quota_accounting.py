"""usage periods and concurrency-safe job quota accounting

Revision ID: 019_usage_quota_accounting
Revises: 018_membership_subscriptions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "019_usage_quota_accounting"
down_revision: str | None = "018_membership_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QUOTA_TYPES = "'processing_seconds', 'ai_image', 'ai_video', 'export'"


def upgrade() -> None:
    op.add_column(
        "usages",
        sa.Column("processing_seconds_used", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE usages
        SET processing_seconds_used = GREATEST(COALESCE(processing_minutes_used, 0), 0) * 60,
            ai_image_used = GREATEST(COALESCE(ai_image_used, 0), 0),
            ai_video_used = GREATEST(COALESCE(ai_video_used, 0), 0),
            storage_used_mb = GREATEST(COALESCE(storage_used_mb, 0), 0),
            export_used = GREATEST(COALESCE(export_used, 0), 0),
            billing_cycle_start = COALESCE(billing_cycle_start, now()),
            billing_cycle_end = CASE
                WHEN billing_cycle_end IS NULL
                    OR billing_cycle_end <= COALESCE(billing_cycle_start, now())
                THEN COALESCE(billing_cycle_start, now()) + interval '1 month'
                ELSE billing_cycle_end
            END
        """
    )
    # 将已有计数保留在当前月度周期中；首次请求不会因为旧起止时间无效而清零。
    op.execute(
        """
        WITH anchors AS (
            SELECT
                u.id AS usage_id,
                CASE
                    WHEN s.status = 'expired' AND s.current_period_end IS NOT NULL
                    THEN s.current_period_end
                    ELSE s.current_period_start
                END AS anchor
            FROM usages u
            JOIN subscriptions s ON s.user_id = u.user_id
        ),
        offsets AS (
            SELECT
                usage_id,
                anchor,
                GREATEST(
                    0,
                    (
                        EXTRACT(YEAR FROM now())::integer * 12
                        + EXTRACT(MONTH FROM now())::integer
                        - EXTRACT(YEAR FROM anchor)::integer * 12
                        - EXTRACT(MONTH FROM anchor)::integer
                    )
                ) AS month_offset
            FROM anchors
        ),
        periods AS (
            SELECT
                usage_id,
                anchor,
                CASE
                    WHEN anchor + month_offset * interval '1 month' > now()
                    THEN GREATEST(month_offset - 1, 0)
                    ELSE month_offset
                END AS period_offset
            FROM offsets
        )
        UPDATE usages u
        SET billing_cycle_start = p.anchor + p.period_offset * interval '1 month',
            billing_cycle_end = p.anchor + (p.period_offset + 1) * interval '1 month'
        FROM periods p
        WHERE p.usage_id = u.id
        """
    )
    op.drop_column("usages", "processing_minutes_used")
    op.alter_column("usages", "ai_image_used", existing_type=sa.Integer(), nullable=False)
    op.alter_column("usages", "ai_video_used", existing_type=sa.Integer(), nullable=False)
    op.alter_column("usages", "storage_used_mb", existing_type=sa.Float(), nullable=False)
    op.alter_column("usages", "export_used", existing_type=sa.Integer(), nullable=False)
    op.alter_column(
        "usages", "billing_cycle_start", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.alter_column(
        "usages", "billing_cycle_end", existing_type=sa.DateTime(timezone=True), nullable=False
    )

    op.add_column("jobs", sa.Column("quota_type", sa.String(length=30), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("quota_amount", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE jobs
        SET quota_type = 'ai_image', quota_amount = 1
        WHERE type = 'AI 生图分镜'
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET quota_type = 'ai_video', quota_amount = 1
        WHERE type IN ('分镜图 AI 生视频', '示意图特效视频')
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET quota_type = 'export', quota_amount = 1
        WHERE type = '导出'
        """
    )
    op.execute(
        """
        UPDATE jobs j
        SET quota_type = 'processing_seconds',
            quota_amount = GREATEST(CEIL(COALESCE(a.duration, 0))::integer, 1)
        FROM assets a
        WHERE j.type = '素材处理'
          AND a.id = j.payload ->> 'asset_id'
        """
    )
    op.create_check_constraint(
        "ck_jobs_quota_assignment",
        "jobs",
        (
            "(quota_type IS NULL AND quota_amount = 0) OR "
            f"(quota_type IN ({QUOTA_TYPES}) AND quota_amount > 0)"
        ),
    )
    op.create_index("ix_jobs_quota_status", "jobs", ["quota_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_quota_status", table_name="jobs")
    op.drop_constraint("ck_jobs_quota_assignment", "jobs", type_="check")
    op.drop_column("jobs", "quota_amount")
    op.drop_column("jobs", "quota_type")

    op.alter_column(
        "usages", "billing_cycle_end", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.alter_column(
        "usages", "billing_cycle_start", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.alter_column("usages", "export_used", existing_type=sa.Integer(), nullable=True)
    op.alter_column("usages", "storage_used_mb", existing_type=sa.Float(), nullable=True)
    op.alter_column("usages", "ai_video_used", existing_type=sa.Integer(), nullable=True)
    op.alter_column("usages", "ai_image_used", existing_type=sa.Integer(), nullable=True)

    op.add_column(
        "usages",
        sa.Column("processing_minutes_used", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE usages
        SET processing_minutes_used = CEIL(processing_seconds_used / 60.0)::integer
        """
    )
    op.drop_column("usages", "processing_seconds_used")
