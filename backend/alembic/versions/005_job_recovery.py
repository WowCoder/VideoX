"""为异步任务增加可重放参数和恢复元数据。

Revision ID: 005_job_recovery
Revises: 004_real_timestamps
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_job_recovery"
down_revision: Union[str, None] = "004_real_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("payload", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("jobs", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False))
    op.add_column("jobs", sa.Column("celery_task_id", sa.String(length=100), nullable=True))
    op.create_index("ix_jobs_status_updated_at", "jobs", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status_updated_at", table_name="jobs")
    op.drop_column("jobs", "celery_task_id")
    op.drop_column("jobs", "max_attempts")
    op.drop_column("jobs", "attempts")
    op.drop_column("jobs", "payload")
