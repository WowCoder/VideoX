"""收敛已应用旧版 021 后遗留的模型与数据库结构漂移。

Revision ID: 028_reconcile_schema_drift
Revises: 027_user_identities

旧版 021 曾在模型定稿前被部分数据库应用。后续 023 负责新增并回填
正式字段，但没有删除旧字段、替换快照唯一约束，也没有恢复脚本目标
时长的可空语义。本迁移让这些既有数据库与当前 ORM、全新安装保持一致。
"""

from collections.abc import Sequence

from alembic import op


revision: str = "028_reconcile_schema_drift"
down_revision: str | None = "027_user_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(sql: str) -> None:
    """执行静态 PostgreSQL SQL，避免 JSON 中的冒号被解释为绑定参数。"""
    op.get_bind().exec_driver_sql(sql)


def _validate_snapshot_uniqueness() -> None:
    # 旧约束允许同一来源在一次运行中保存多个不同内容的快照，而当前领域
    # 模型只允许一个。遇到真实冲突时必须人工决定保留哪条，不能静默删行。
    _execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM inspiration_source_snapshots
                GROUP BY source_id, run_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    MESSAGE = '028_reconcile_schema_drift: inspiration_source_snapshots '
                              '存在重复的 (source_id, run_id)，请先人工合并后重试';
            END IF;
        END $$
        """
    )


def _ensure_migration_audits_table() -> None:
    # 旧版 021 数据库可能连迁移审计表本身也没有创建；当前 021 和演练工具
    # 都将它视为正式迁移基础设施，因此在收敛前先补齐。
    _execute(
        """
        CREATE TABLE IF NOT EXISTS migration_audits (
            id varchar(64) PRIMARY KEY,
            migration_name varchar(100) NOT NULL,
            entity_type varchar(50) NOT NULL,
            source_id varchar(64),
            target_id varchar(64),
            action varchar(50) NOT NULL,
            details json NOT NULL DEFAULT '{}'::json,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    _execute(
        "CREATE INDEX IF NOT EXISTS ix_migration_audits_migration_name "
        "ON migration_audits (migration_name)"
    )
    _execute(
        "CREATE INDEX IF NOT EXISTS ix_migration_audits_source_id "
        "ON migration_audits (source_id)"
    )


def _archive_and_drop_legacy_columns() -> None:
    # 仅归档有信息量的非默认值；归档记录使用确定性 ID，便于失败重试。
    # 每个字段独立检查，使迁移同时适用于旧版 021 数据库和全新数据库。
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
                    INSERT INTO migration_audits (
                        id, migration_name, entity_type, source_id, action, details
                    )
                    SELECT
                        'audit-' || substr(md5('028:inspiration_tasks:goal:' || id), 1, 24),
                        '028_reconcile_schema_drift',
                        'inspiration_task',
                        id,
                        'archived_legacy_column',
                        json_build_object('column', 'goal', 'value', goal)
                    FROM inspiration_tasks
                    WHERE COALESCE(goal, '') <> ''
                    ON CONFLICT (id) DO NOTHING
                $sql$;
                ALTER TABLE inspiration_tasks DROP COLUMN goal;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspiration_tasks'
                  AND column_name = 'schedule_minutes'
            ) THEN
                EXECUTE $sql$
                    INSERT INTO migration_audits (
                        id, migration_name, entity_type, source_id, action, details
                    )
                    SELECT
                        'audit-' || substr(md5('028:inspiration_tasks:schedule_minutes:' || id), 1, 24),
                        '028_reconcile_schema_drift',
                        'inspiration_task',
                        id,
                        'archived_legacy_column',
                        json_build_object('column', 'schedule_minutes', 'value', schedule_minutes)
                    FROM inspiration_tasks
                    WHERE schedule_minutes IS DISTINCT FROM 1440
                    ON CONFLICT (id) DO NOTHING
                $sql$;
                ALTER TABLE inspiration_tasks DROP COLUMN schedule_minutes;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspiration_tasks'
                  AND column_name = 'filters'
            ) THEN
                EXECUTE $sql$
                    INSERT INTO migration_audits (
                        id, migration_name, entity_type, source_id, action, details
                    )
                    SELECT
                        'audit-' || substr(md5('028:inspiration_tasks:filters:' || id), 1, 24),
                        '028_reconcile_schema_drift',
                        'inspiration_task',
                        id,
                        'archived_legacy_column',
                        json_build_object('column', 'filters', 'value', filters)
                    FROM inspiration_tasks
                    WHERE COALESCE(filters::jsonb, '{}'::jsonb) <> '{}'::jsonb
                    ON CONFLICT (id) DO NOTHING
                $sql$;
                ALTER TABLE inspiration_tasks DROP COLUMN filters;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspiration_results'
                  AND column_name = 'topic_suggestion'
            ) THEN
                EXECUTE $sql$
                    INSERT INTO migration_audits (
                        id, migration_name, entity_type, source_id, action, details
                    )
                    SELECT
                        'audit-' || substr(md5('028:inspiration_results:topic_suggestion:' || id), 1, 24),
                        '028_reconcile_schema_drift',
                        'inspiration_result',
                        id,
                        'archived_legacy_column',
                        json_build_object('column', 'topic_suggestion', 'value', topic_suggestion)
                    FROM inspiration_results
                    WHERE COALESCE(topic_suggestion, '') <> ''
                    ON CONFLICT (id) DO NOTHING
                $sql$;
                ALTER TABLE inspiration_results DROP COLUMN topic_suggestion;
            END IF;
        END $$
        """
    )


def _replace_snapshot_constraint() -> None:
    _execute(
        """
        ALTER TABLE inspiration_source_snapshots
            DROP CONSTRAINT IF EXISTS uq_inspiration_source_content_hash
        """
    )
    _execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'inspiration_source_snapshots'::regclass
                  AND conname = 'uq_inspiration_source_run'
            ) THEN
                ALTER TABLE inspiration_source_snapshots
                    ADD CONSTRAINT uq_inspiration_source_run UNIQUE (source_id, run_id);
            END IF;
        END $$
        """
    )


def upgrade() -> None:
    _validate_snapshot_uniqueness()
    _ensure_migration_audits_table()
    _archive_and_drop_legacy_columns()
    _replace_snapshot_constraint()
    op.alter_column(
        "scripts",
        "target_duration_seconds",
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    raise RuntimeError(
        "028_reconcile_schema_drift 会归档并移除不再使用的旧字段，迁移不可自动回退。"
    )
