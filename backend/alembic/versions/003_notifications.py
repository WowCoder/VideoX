"""真实站内通知与任务终态触发器。

Revision ID: 003_notifications
Revises: 002_project_timeline
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_notifications"
down_revision: Union[str, None] = "002_project_timeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=50), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("type", sa.String(length=30), server_default="info", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), server_default="", nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # 所有 Worker 最终都会更新 jobs.status；数据库触发器保证任何真实成功/失败
    # 都生成且只生成一条通知，不依赖某个 Worker 是否记得显式写通知。
    op.execute(
        """
        CREATE OR REPLACE FUNCTION create_job_terminal_notification()
        RETURNS trigger AS $$
        DECLARE
            owner_user_id varchar(50);
        BEGIN
            IF NEW.status IN ('SUCCEEDED', 'FAILED')
               AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT owner_id INTO owner_user_id
                FROM projects
                WHERE id = NEW.project_id;

                IF owner_user_id IS NOT NULL THEN
                    INSERT INTO notifications (
                        id, user_id, project_id, job_id, type, title,
                        message, link, is_read, created_at
                    ) VALUES (
                        'notification-' || substr(md5(random()::text || clock_timestamp()::text), 1, 12),
                        owner_user_id,
                        NEW.project_id,
                        NEW.id,
                        CASE WHEN NEW.status = 'SUCCEEDED' THEN 'success' ELSE 'error' END,
                        CASE
                            WHEN NEW.status = 'SUCCEEDED' THEN NEW.name || '已完成'
                            ELSE NEW.name || '失败'
                        END,
                        COALESCE(NULLIF(NEW.result_detail, ''), NULLIF(NEW.detail, ''),
                            CASE WHEN NEW.status = 'SUCCEEDED' THEN '任务已完成' ELSE '任务执行失败' END),
                        '/workspace/projects/' || NEW.project_id,
                        false,
                        now()
                    );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER jobs_terminal_notification_trigger
        AFTER UPDATE OF status ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION create_job_terminal_notification()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS jobs_terminal_notification_trigger ON jobs")
    op.execute("DROP FUNCTION IF EXISTS create_job_terminal_notification")
    op.drop_table("notifications")
