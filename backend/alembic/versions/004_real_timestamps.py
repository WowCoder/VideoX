"""将项目、脚本和素材的展示字符串迁移为真实时间戳。

Revision ID: 004_real_timestamps
Revises: 003_notifications
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op


revision: str = "004_real_timestamps"
down_revision: Union[str, None] = "003_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧字段只保存“刚刚”等展示文案，不包含可恢复的绝对时间。
    # 使用每条记录真实的 created_at 作为迁移基线，避免编造历史时间。
    op.execute("ALTER TABLE projects ALTER COLUMN updated_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN updated_at TYPE timestamptz "
        "USING created_at"
    )
    op.execute("ALTER TABLE projects ALTER COLUMN updated_at SET DEFAULT now()")

    op.execute("ALTER TABLE scripts ALTER COLUMN updated_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE scripts ALTER COLUMN updated_at TYPE timestamptz "
        "USING created_at"
    )
    op.execute("ALTER TABLE scripts ALTER COLUMN updated_at SET DEFAULT now()")

    op.execute("ALTER TABLE assets ALTER COLUMN uploaded_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN uploaded_at TYPE timestamptz "
        "USING created_at"
    )
    op.execute("ALTER TABLE assets ALTER COLUMN uploaded_at SET DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE assets ALTER COLUMN uploaded_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN uploaded_at TYPE varchar(50) "
        "USING to_char(uploaded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
    )
    op.execute("ALTER TABLE assets ALTER COLUMN uploaded_at SET DEFAULT '刚刚'")

    op.execute("ALTER TABLE scripts ALTER COLUMN updated_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE scripts ALTER COLUMN updated_at TYPE varchar(50) "
        "USING to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
    )
    op.execute("ALTER TABLE scripts ALTER COLUMN updated_at SET DEFAULT '刚刚'")

    op.execute("ALTER TABLE projects ALTER COLUMN updated_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN updated_at TYPE varchar(50) "
        "USING to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
    )
    op.execute("ALTER TABLE projects ALTER COLUMN updated_at SET DEFAULT '刚刚'")
