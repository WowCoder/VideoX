"""视频生成批次、非阻塞调度状态与幂等字段。

Revision ID: 033_video_generation_queue
Revises: 032_admin_activity_metrics
"""

from alembic import op
import sqlalchemy as sa


revision = "033_video_generation_queue"
down_revision = "032_admin_activity_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_generation_batches",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("cancelled_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_generation_batches_owner_id", "video_generation_batches", ["owner_id"])
    op.create_index("ix_video_generation_batches_project_id", "video_generation_batches", ["project_id"])
    op.create_index("ix_video_generation_batches_status", "video_generation_batches", ["status"])
    op.create_index("ix_video_generation_batches_last_dispatched_at", "video_generation_batches", ["last_dispatched_at"])
    op.create_index("ix_video_batches_owner_created", "video_generation_batches", ["owner_id", "created_at"])
    op.create_index("ix_video_batches_project_created", "video_generation_batches", ["project_id", "created_at"])

    columns = (
        ("batch_id", sa.String(length=64)),
        ("execution_state", sa.String(length=30)),
        ("idempotency_key", sa.String(length=128)),
        ("provider_task_id", sa.String(length=255)),
        ("queued_at", sa.DateTime(timezone=True)),
        ("heartbeat_at", sa.DateTime(timezone=True)),
        ("submitted_at", sa.DateTime(timezone=True)),
        ("last_polled_at", sa.DateTime(timezone=True)),
        ("provider_finished_at", sa.DateTime(timezone=True)),
        ("next_poll_at", sa.DateTime(timezone=True)),
        ("submit_attempts", sa.Integer()),
        ("poll_attempts", sa.Integer()),
    )
    for name, column_type in columns:
        op.add_column("jobs", sa.Column(name, column_type, nullable=True))
    op.create_foreign_key(
        "fk_jobs_video_batch_id",
        "jobs", "video_generation_batches", ["batch_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "uq_jobs_active_idempotency_key",
        "jobs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING', 'PAUSED')"),
        sqlite_where=sa.text("status IN ('QUEUED', 'RUNNING', 'PAUSED')"),
    )
    for column in ("batch_id", "execution_state", "provider_task_id", "queued_at", "next_poll_at"):
        op.create_index(f"ix_jobs_{column}", "jobs", [column])
    op.create_index("ix_jobs_video_dispatch", "jobs", ["type", "execution_state", "queued_at"])
    op.create_index("ix_jobs_video_inflight_owner", "jobs", ["owner_id", "execution_state"])
    op.create_index("ix_jobs_video_inflight_project", "jobs", ["project_id", "execution_state"])
    op.execute("UPDATE jobs SET queued_at = created_at WHERE queued_at IS NULL")
    op.execute(
        "UPDATE jobs SET execution_state = CASE "
        "WHEN status = 'QUEUED' THEN 'QUEUED' "
        "WHEN status = 'RUNNING' THEN 'RUNNING_LEGACY' "
        "ELSE status END "
        "WHERE type = '分镜图 AI 生视频' AND execution_state IS NULL"
    )
    op.execute("UPDATE jobs SET submit_attempts = 0 WHERE submit_attempts IS NULL")
    op.execute("UPDATE jobs SET poll_attempts = 0 WHERE poll_attempts IS NULL")
    op.alter_column("jobs", "submit_attempts", server_default=sa.text("0"), nullable=False)
    op.alter_column("jobs", "poll_attempts", server_default=sa.text("0"), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_video_inflight_project", table_name="jobs")
    op.drop_index("ix_jobs_video_inflight_owner", table_name="jobs")
    op.drop_index("ix_jobs_video_dispatch", table_name="jobs")
    for column in ("next_poll_at", "queued_at", "provider_task_id", "execution_state", "batch_id"):
        op.drop_index(f"ix_jobs_{column}", table_name="jobs")
    op.drop_index("uq_jobs_active_idempotency_key", table_name="jobs")
    op.drop_constraint("fk_jobs_video_batch_id", "jobs", type_="foreignkey")
    for column in (
        "poll_attempts", "submit_attempts", "next_poll_at", "provider_finished_at",
        "last_polled_at", "submitted_at", "heartbeat_at", "queued_at",
        "provider_task_id", "idempotency_key", "execution_state", "batch_id",
    ):
        op.drop_column("jobs", column)
    op.drop_index("ix_video_generation_batches_last_dispatched_at", table_name="video_generation_batches")
    op.drop_table("video_generation_batches")
