"""运营后台额度、支付、发票、订阅和任务可观测字段。

Revision ID: 031_admin_mvp_operations
Revises: 030_admin_mvp_foundation
"""

from alembic import op
import sqlalchemy as sa


revision = "031_admin_mvp_operations"
down_revision = "030_admin_mvp_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quota_adjustments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("quota_type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("related_job_id", sa.String(length=64), nullable=True),
        sa.Column("admin_user_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quota_type IN ('processing_seconds', 'ai_image', 'ai_video', 'export')",
            name="ck_quota_adjustments_type",
        ),
        sa.CheckConstraint("amount > 0", name="ck_quota_adjustments_positive"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["related_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "admin_user_id", "idempotency_key", name="uq_quota_adjustments_idempotency"
        ),
    )
    op.create_index("ix_quota_adjustments_user_id", "quota_adjustments", ["user_id"])
    op.create_index("ix_quota_adjustments_quota_type", "quota_adjustments", ["quota_type"])
    op.create_index("ix_quota_adjustments_expires_at", "quota_adjustments", ["expires_at"])
    op.create_index("ix_quota_adjustments_related_job_id", "quota_adjustments", ["related_job_id"])
    op.create_index("ix_quota_adjustments_admin_user_id", "quota_adjustments", ["admin_user_id"])
    op.create_index(
        "ix_quota_adjustments_user_active",
        "quota_adjustments",
        ["user_id", "effective_at", "expires_at"],
    )

    op.create_table(
        "subscription_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("subscription_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=False),
        sa.Column("after_data", sa.JSON(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("admin_user_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscription_events_user_id", "subscription_events", ["user_id"])
    op.create_index("ix_subscription_events_subscription_id", "subscription_events", ["subscription_id"])
    op.create_index("ix_subscription_events_event_type", "subscription_events", ["event_type"])
    op.create_index("ix_subscription_events_order_id", "subscription_events", ["order_id"])
    op.create_index("ix_subscription_events_admin_user_id", "subscription_events", ["admin_user_id"])
    op.create_index(
        "ix_subscription_events_user_created", "subscription_events", ["user_id", "created_at"]
    )

    op.add_column("orders", sa.Column("provider", sa.String(length=50), server_default="alipay", nullable=False))
    op.add_column("orders", sa.Column("provider_trade_no", sa.String(length=128), nullable=True))
    op.add_column("orders", sa.Column("provider_status", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("paid_amount", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("notify_received_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_orders_provider_trade_no", "orders", ["provider_trade_no"])

    op.add_column("invoices", sa.Column("invoice_number", sa.String(length=100), nullable=True))
    op.add_column("invoices", sa.Column("document_path", sa.String(length=1000), nullable=True))
    op.add_column("invoices", sa.Column("handled_by_admin_id", sa.String(length=64), nullable=True))
    op.add_column("invoices", sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_invoices_handled_by_admin_id",
        "invoices", "admin_users", ["handled_by_admin_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_invoices_handled_by_admin_id", "invoices", ["handled_by_admin_id"])
    op.create_unique_constraint("uq_invoices_invoice_number", "invoices", ["invoice_number"])

    for name, column in (
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)),
        ("finished_at", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)),
        ("error_code", sa.Column("error_code", sa.String(length=80), nullable=True)),
        ("error_category", sa.Column("error_category", sa.String(length=80), nullable=True)),
        ("provider", sa.Column("provider", sa.String(length=80), nullable=True)),
        ("model", sa.Column("model", sa.String(length=160), nullable=True)),
        ("provider_request_id", sa.Column("provider_request_id", sa.String(length=255), nullable=True)),
    ):
        op.add_column("jobs", column)
    op.create_index("ix_jobs_error_code", "jobs", ["error_code"])
    op.create_index("ix_jobs_error_category", "jobs", ["error_category"])
    op.create_index("ix_jobs_provider", "jobs", ["provider"])
    op.create_index("ix_jobs_provider_request_id", "jobs", ["provider_request_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_provider_request_id", table_name="jobs")
    op.drop_index("ix_jobs_provider", table_name="jobs")
    op.drop_index("ix_jobs_error_category", table_name="jobs")
    op.drop_index("ix_jobs_error_code", table_name="jobs")
    for column in (
        "provider_request_id", "model", "provider", "error_category", "error_code", "finished_at", "started_at"
    ):
        op.drop_column("jobs", column)
    op.drop_constraint("uq_invoices_invoice_number", "invoices", type_="unique")
    op.drop_index("ix_invoices_handled_by_admin_id", table_name="invoices")
    op.drop_constraint("fk_invoices_handled_by_admin_id", "invoices", type_="foreignkey")
    for column in ("sent_at", "handled_at", "handled_by_admin_id", "document_path", "invoice_number"):
        op.drop_column("invoices", column)
    op.drop_constraint("uq_orders_provider_trade_no", "orders", type_="unique")
    for column in ("notify_received_at", "paid_amount", "provider_status", "provider_trade_no", "provider"):
        op.drop_column("orders", column)
    op.drop_table("subscription_events")
    op.drop_table("quota_adjustments")
