"""增加用户通知偏好。

Revision ID: 006_user_settings
Revises: 005_job_recovery
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_user_settings"
down_revision: Union[str, None] = "005_job_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notify_asset_processing", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("notify_script_generation", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("notify_marketing", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_marketing")
    op.drop_column("users", "notify_script_generation")
    op.drop_column("users", "notify_asset_processing")
