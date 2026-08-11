"""Team membership seats

Revision ID: 020_team_seats
Revises: 019_usage_quota_accounting
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "020_team_seats"
down_revision: str | None = "019_usage_quota_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("seat_quota", sa.Integer(), server_default="1", nullable=False),
    )
    op.execute("UPDATE memberships SET seat_quota = CASE WHEN rank >= 2 THEN 5 ELSE 1 END")
    op.create_check_constraint(
        "ck_memberships_seat_quota_positive",
        "memberships",
        "seat_quota >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_memberships_seat_quota_positive", "memberships", type_="check"
    )
    op.drop_column("memberships", "seat_quota")
