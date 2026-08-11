"""membership subscriptions and billing periods

Revision ID: 018_membership_subscriptions
Revises: 017_cut_versions_history
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "018_membership_subscriptions"
down_revision: str | None = "017_cut_versions_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("membership_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("billing_cycle", sa.String(length=20), server_default="permanent", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider", sa.String(length=50), server_default="system", nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("latest_order_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly', 'permanent')",
            name="ck_subscriptions_billing_cycle",
        ),
        sa.CheckConstraint(
            "current_period_end IS NULL OR current_period_end > current_period_start",
            name="ck_subscriptions_period_order",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'internal', 'past_due', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        sa.ForeignKeyConstraint(["latest_order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_membership_id", "subscriptions", ["membership_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_current_period_end", "subscriptions", ["current_period_end"])

    # 旧账号没有可信的支付周期：Free 视为永久免费，付费等级视为内部长期会员。
    op.execute(
        """
        INSERT INTO subscriptions (
            id, user_id, membership_id, status, billing_cycle,
            current_period_start, current_period_end, auto_renew,
            cancel_at_period_end, provider, created_at, updated_at
        )
        SELECT
            'subscription-' || substr(md5(random()::text || u.id), 1, 12),
            u.id,
            u.membership_id,
            CASE WHEN COALESCE(m.rank, 0) = 0 THEN 'active' ELSE 'internal' END,
            'permanent',
            COALESCE(u.created_at, now()),
            NULL,
            false,
            false,
            CASE WHEN COALESCE(m.rank, 0) = 0 THEN 'system' ELSE 'internal' END,
            now(),
            now()
        FROM users u
        LEFT JOIN memberships m ON m.id = u.membership_id
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_current_period_end", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_membership_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
