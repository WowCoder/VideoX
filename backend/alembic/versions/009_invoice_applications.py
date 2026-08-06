"""invoice applications

Revision ID: 009_invoice_applications
Revises: 008_project_collaboration
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "009_invoice_applications"
down_revision: str | None = "008_project_collaboration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("tax_number", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="requested"),
        sa.Column("reject_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_invoices_order_id"),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
    op.create_index("ix_invoices_order_id", "invoices", ["order_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])


def downgrade() -> None:
    op.drop_table("invoices")
