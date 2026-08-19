"""Reconcile workspace columns added after revision 021 was first applied.

Revision ID: 023_reconcile_workspace
Revises: 022_normalize_workspace

The workspace and inspiration models evolved while revision 021 was still
under development.  Databases which had already applied that revision keep
the old table shape because Alembic never re-runs an applied migration.  Use
``IF NOT EXISTS`` here so both those databases and fresh installations (where
021 already creates the columns) converge on the same schema.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "023_reconcile_workspace"
down_revision: str | None = "022_normalize_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(sql: str) -> None:
    """Execute static PostgreSQL SQL without interpreting JSON colons as binds."""
    op.get_bind().exec_driver_sql(sql)


def upgrade() -> None:
    _execute(
        """
        ALTER TABLE project_compositions
            ADD COLUMN IF NOT EXISTS timeline json NOT NULL
                DEFAULT '{"duration_ms":0,"tracks":[]}'::json,
            ADD COLUMN IF NOT EXISTS visual_layers json NOT NULL
                DEFAULT '{"items":[]}'::json,
            ADD COLUMN IF NOT EXISTS global_scopes json NOT NULL
                DEFAULT '{"film":{},"scenes":{}}'::json,
            ADD COLUMN IF NOT EXISTS workflow_graph json NOT NULL
                DEFAULT '{"nodes":[],"edges":[]}'::json
        """
    )

    # Add the new task contract as nullable first, backfill any rows created
    # with the earlier goal/schedule_minutes contract, then enforce the model's
    # non-null guarantees.
    _execute(
        """
        ALTER TABLE inspiration_tasks
            ADD COLUMN IF NOT EXISTS task_type varchar(40),
            ADD COLUMN IF NOT EXISTS topic_brief text,
            ADD COLUMN IF NOT EXISTS topic_count integer,
            ADD COLUMN IF NOT EXISTS schedule json
        """
    )
    _execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspiration_tasks'
                  AND column_name = 'goal'
            ) THEN
                EXECUTE $sql$
                    UPDATE inspiration_tasks
                    SET topic_brief = goal
                    WHERE topic_brief IS NULL OR topic_brief = ''
                $sql$;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspiration_tasks'
                  AND column_name = 'schedule_minutes'
            ) THEN
                EXECUTE $sql$
                    UPDATE inspiration_tasks
                    SET schedule = CASE
                        WHEN schedule_minutes IS NULL OR schedule_minutes <= 0
                            THEN '{"type":"manual","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}'::json
                        WHEN schedule_minutes >= 10080
                            THEN '{"type":"weekly","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}'::json
                        ELSE '{"type":"daily","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}'::json
                    END
                    WHERE schedule IS NULL
                $sql$;
            END IF;
        END $$
        """
    )
    _execute(
        """
        UPDATE inspiration_tasks
        SET task_type = COALESCE(task_type, 'topic-recommendation'),
            topic_brief = COALESCE(topic_brief, ''),
            topic_count = CASE
                WHEN COALESCE(task_type, 'topic-recommendation') = 'topic-recommendation'
                    THEN COALESCE(topic_count, 5)
                ELSE NULL
            END,
            schedule = COALESCE(
                schedule,
                '{"type":"daily","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}'::json
            )
        """
    )
    _execute(
        """
        ALTER TABLE inspiration_tasks
            ALTER COLUMN task_type SET NOT NULL,
            ALTER COLUMN topic_brief SET NOT NULL,
            ALTER COLUMN schedule SET NOT NULL,
            ALTER COLUMN topic_brief SET DEFAULT '',
            ALTER COLUMN schedule SET DEFAULT
                '{"type":"daily","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}'::json
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inspiration_tasks_task_type "
        "ON inspiration_tasks (task_type)"
    )

def downgrade() -> None:
    raise RuntimeError(
        "023_reconcile_workspace repairs already-applied schema history and is intentionally irreversible."
    )
