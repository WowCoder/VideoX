"""Attach V-Credits quote/hold references to jobs.

Revision ID: 035_job_billing_v2_fields
Revises: 034_billing_v2_foundation
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "035_job_billing_v2_fields"
down_revision: str | None = "034_billing_v2_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("billing_quote_id", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("billing_hold_id", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("quoted_credits", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("billed_credits", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key(
        "fk_jobs_billing_quote_id",
        "jobs",
        "billing_quotes",
        ["billing_quote_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_jobs_billing_hold_id",
        "jobs",
        "credit_holds",
        ["billing_hold_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_billing_quote_id", "jobs", ["billing_quote_id"])
    op.create_index("ix_jobs_billing_hold_id", "jobs", ["billing_hold_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_billing_hold_id", table_name="jobs")
    op.drop_index("ix_jobs_billing_quote_id", table_name="jobs")
    op.drop_constraint("fk_jobs_billing_hold_id", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_billing_quote_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "billed_credits")
    op.drop_column("jobs", "quoted_credits")
    op.drop_column("jobs", "billing_hold_id")
    op.drop_column("jobs", "billing_quote_id")
