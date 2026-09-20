"""Persist catalog/product price snapshots on orders.

Revision ID: 036_order_billing_v2_snapshot
Revises: 035_job_billing_v2_fields
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "036_order_billing_v2_snapshot"
down_revision: str | None = "035_job_billing_v2_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("catalog_version_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("product_type", sa.String(30), server_default="membership", nullable=False))
    op.add_column("orders", sa.Column("product_code", sa.String(120), nullable=True))
    op.add_column("orders", sa.Column("price_fen", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("credit_amount", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_orders_billing_catalog_version_id",
        "orders",
        "billing_catalog_versions",
        ["catalog_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_orders_catalog_version_id", "orders", ["catalog_version_id"])
    op.execute("UPDATE orders SET product_type = 'membership' WHERE product_type IS NULL")


def downgrade() -> None:
    op.drop_index("ix_orders_catalog_version_id", table_name="orders")
    op.drop_constraint("fk_orders_billing_catalog_version_id", "orders", type_="foreignkey")
    op.drop_column("orders", "credit_amount")
    op.drop_column("orders", "price_fen")
    op.drop_column("orders", "product_code")
    op.drop_column("orders", "product_type")
    op.drop_column("orders", "catalog_version_id")
