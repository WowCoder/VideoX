"""Versioned OpenVMA commercial catalog and V-Credits wallet.

Revision ID: 034_billing_v2_foundation
Revises: 033_video_generation_queue
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa


revision: str = "034_billing_v2_foundation"
down_revision: str | None = "033_video_generation_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMPTY_JSON = {}


def upgrade() -> None:
    op.create_table(
        "billing_catalog_versions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("version_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.String(64), nullable=True),
        sa.Column("published_by_admin_id", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published', 'retired')", name="ck_billing_catalog_versions_status"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_key", name="uq_billing_catalog_versions_key"),
    )
    op.create_index("ix_billing_catalog_versions_status_effective", "billing_catalog_versions", ["status", "effective_at"])

    op.create_table(
        "billing_plan_versions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("membership_id", sa.String(50), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("monthly_price_fen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("annual_price_fen", sa.Integer(), nullable=True),
        sa.Column("monthly_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("signup_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rollover_cycles", sa.Integer(), server_default="3", nullable=False),
        sa.Column("recharge_bonus_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("generation_concurrency", sa.Integer(), server_default="1", nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("seat_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("queue_priority", sa.Integer(), server_default="9", nullable=False),
        sa.Column("model_access_level", sa.String(50), server_default="basic", nullable=False),
        sa.Column("max_video_resolution", sa.String(20), server_default="720p", nullable=False),
        sa.Column("max_image_resolution", sa.String(20), server_default="1k", nullable=False),
        sa.Column("watermark_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("commercial_use", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("api_access", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("batch_access", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("rollover_policy", sa.String(50), server_default="three_cycles", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("monthly_price_fen >= 0", name="ck_billing_plan_versions_monthly_price"),
        sa.CheckConstraint("annual_price_fen IS NULL OR annual_price_fen >= 0", name="ck_billing_plan_versions_annual_price"),
        sa.CheckConstraint("monthly_credits >= 0", name="ck_billing_plan_versions_monthly_credits"),
        sa.CheckConstraint("signup_credits >= 0", name="ck_billing_plan_versions_signup_credits"),
        sa.CheckConstraint("recharge_bonus_bps >= 0", name="ck_billing_plan_versions_bonus"),
        sa.CheckConstraint("generation_concurrency >= 1", name="ck_billing_plan_versions_concurrency"),
        sa.CheckConstraint("storage_bytes >= 0", name="ck_billing_plan_versions_storage"),
        sa.CheckConstraint("seat_limit >= 1", name="ck_billing_plan_versions_seats"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "plan_code", name="uq_billing_plan_versions_code"),
    )
    op.create_index("ix_billing_plan_versions_catalog_rank", "billing_plan_versions", ["catalog_version_id", "rank"])
    op.create_index("ix_billing_plan_versions_membership_id", "billing_plan_versions", ["membership_id"])

    op.create_table(
        "credit_packages",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("package_code", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("price_fen", sa.Integer(), nullable=False),
        sa.Column("base_credits", sa.Integer(), nullable=False),
        sa.Column("package_bonus_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("price_fen > 0", name="ck_credit_packages_price"),
        sa.CheckConstraint("base_credits > 0", name="ck_credit_packages_credits"),
        sa.CheckConstraint("package_bonus_bps >= 0", name="ck_credit_packages_bonus"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "package_code", name="uq_credit_packages_code"),
    )

    op.create_table(
        "billable_skus",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("sku", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("minimum_quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rounding_mode", sa.String(30), server_default="ceil", nullable=False),
        sa.Column("access_level", sa.String(50), server_default="basic", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "sku", name="uq_billable_skus_sku"),
    )

    op.create_table(
        "rate_card_entries",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("sku_id", sa.String(64), nullable=False),
        sa.Column("credits_per_unit", sa.Integer(), nullable=False),
        sa.Column("minimum_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("allowed_plan_codes", sa.JSON(), nullable=False),
        sa.Column("included_in_pass", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("credits_per_unit > 0", name="ck_rate_card_entries_positive"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["billable_skus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "sku_id", name="uq_rate_card_entries_sku"),
    )

    op.create_table(
        "pass_products",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("pass_code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("price_fen", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("model_patterns", sa.JSON(), nullable=False),
        sa.Column("resolution_limit", sa.String(20), server_default="720p", nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("fair_use_limit", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("price_fen > 0", name="ck_pass_products_price"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_pass_products_duration"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_version_id", "pass_code", name="uq_pass_products_code"),
    )

    op.create_table(
        "billing_accounts",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("cached_available_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cached_reserved_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("owner_type IN ('user', 'team', 'enterprise')", name="ck_billing_accounts_owner_type"),
        sa.CheckConstraint("cached_available_credits >= 0", name="ck_billing_accounts_available"),
        sa.CheckConstraint("cached_reserved_credits >= 0", name="ck_billing_accounts_reserved"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_billing_accounts_owner"),
    )

    op.create_table(
        "credit_lots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("billing_account_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("original_amount", sa.Integer(), nullable=False),
        sa.Column("remaining_amount", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_version_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("original_amount > 0", name="ck_credit_lots_original_positive"),
        sa.CheckConstraint("remaining_amount >= 0", name="ck_credit_lots_remaining_nonnegative"),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_lots_account_expiry", "credit_lots", ["billing_account_id", "expires_at"])

    op.create_table(
        "billing_quotes",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("billing_account_id", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.String(64), nullable=False),
        sa.Column("total_credits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), server_default="CREDITS", nullable=False),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="issued", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("total_credits > 0", name="ck_billing_quotes_positive"),
        sa.CheckConstraint("status IN ('issued', 'consumed', 'expired', 'cancelled')", name="ck_billing_quotes_status"),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["billing_catalog_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_quotes_account_expires", "billing_quotes", ["billing_account_id", "expires_at"])

    op.create_table(
        "billing_quote_lines",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("quote_id", sa.String(64), nullable=False),
        sa.Column("sku_id", sa.String(64), nullable=False),
        sa.Column("sku", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_credits", sa.Integer(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_billing_quote_lines_quantity"),
        sa.ForeignKeyConstraint(["quote_id"], ["billing_quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["billable_skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_quote_lines_quote_id", "billing_quote_lines", ["quote_id"])

    op.create_table(
        "credit_holds",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("billing_account_id", sa.String(64), nullable=False),
        sa.Column("quote_id", sa.String(64), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_credit_holds_positive"),
        sa.CheckConstraint("status IN ('active', 'captured', 'released', 'expired')", name="ck_credit_holds_status"),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["billing_quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_credit_holds_idempotency"),
    )

    op.create_table(
        "credit_hold_items",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("hold_id", sa.String(64), nullable=False),
        sa.Column("credit_lot_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_credit_hold_items_positive"),
        sa.ForeignKeyConstraint(["hold_id"], ["credit_holds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credit_lot_id"], ["credit_lots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hold_id", "credit_lot_id", name="uq_credit_hold_items_lot"),
    )

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("billing_account_id", sa.String(64), nullable=False),
        sa.Column("credit_lot_id", sa.String(64), nullable=True),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("quote_id", sa.String(64), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credit_lot_id"], ["credit_lots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_id"], ["billing_quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("billing_account_id", "idempotency_key", name="uq_credit_ledger_idempotency"),
    )
    op.create_index("ix_credit_ledger_account_created", "credit_ledger", ["billing_account_id", "created_at"])

    # Add the new membership identities without changing legacy rows or active users.
    op.execute(
        """
        INSERT INTO memberships (id, name, rank, billing_cycle, processing_minutes,
            ai_image_quota, ai_video_quota, storage_gb, export_quota, price, payment_method)
        VALUES
            ('membership-creator', 'Creator', 1, 'monthly', 0, 0, 0, 50, 0, 39.0, NULL),
            ('membership-studio', 'Studio', 3, 'monthly', 0, 0, 0, 1000, 0, 299.0, NULL)
        ON CONFLICT (id) DO NOTHING
        """
    )
    # 对旧迁移已经存在的 Pro/Team 会员同步新的商业档位顺序和人民币
    # 价格；旧 quota_* 字段仍保留给迁移期兼容逻辑，不作为 V2 计费依据。
    op.execute(
        """
        UPDATE memberships
        SET rank = 2, name = 'Pro', price = 99.0, storage_gb = 200
        WHERE id = 'membership-pro'
        """
    )
    op.execute(
        """
        UPDATE memberships
        SET rank = 4, name = 'Team', price = 699.0, storage_gb = 2000
        WHERE id = 'membership-team'
        """
    )

    op.execute(
        """
        INSERT INTO billing_catalog_versions (id, version_key, status, effective_at, published_at, notes)
        VALUES ('catalog-v1', 'openvma-2026-09-02-v1', 'published', now(), now(), 'Initial V-Credits catalog derived from OpenVMA commercial plan')
        ON CONFLICT (version_key) DO NOTHING
        """
    )

    plan_rows = sa.table(
        "billing_plan_versions",
        sa.column("id", sa.String), sa.column("catalog_version_id", sa.String), sa.column("plan_code", sa.String),
        sa.column("membership_id", sa.String), sa.column("display_name", sa.String), sa.column("rank", sa.Integer),
        sa.column("monthly_price_fen", sa.Integer), sa.column("annual_price_fen", sa.Integer), sa.column("monthly_credits", sa.Integer),
        sa.column("signup_credits", sa.Integer), sa.column("rollover_cycles", sa.Integer), sa.column("recharge_bonus_bps", sa.Integer),
        sa.column("generation_concurrency", sa.Integer), sa.column("storage_bytes", sa.BigInteger), sa.column("seat_limit", sa.Integer),
        sa.column("queue_priority", sa.Integer), sa.column("model_access_level", sa.String), sa.column("max_video_resolution", sa.String),
        sa.column("max_image_resolution", sa.String), sa.column("watermark_required", sa.Boolean), sa.column("commercial_use", sa.Boolean),
        sa.column("api_access", sa.Boolean), sa.column("batch_access", sa.Boolean), sa.column("rollover_policy", sa.String), sa.column("metadata_json", sa.JSON),
    )
    op.bulk_insert(
        plan_rows,
        [
            dict(id="planv-v1-free", catalog_version_id="catalog-v1", plan_code="free", membership_id="membership-free", display_name="Free", rank=0, monthly_price_fen=0, annual_price_fen=0, monthly_credits=0, signup_credits=300, rollover_cycles=0, recharge_bonus_bps=0, generation_concurrency=1, storage_bytes=2 * 1024**3, seat_limit=1, queue_priority=9, model_access_level="basic", max_video_resolution="720p_preview", max_image_resolution="1k", watermark_required=True, commercial_use=False, api_access=False, batch_access=False, rollover_policy="none", metadata_json=EMPTY_JSON),
            dict(id="planv-v1-creator", catalog_version_id="catalog-v1", plan_code="creator", membership_id="membership-creator", display_name="Creator", rank=1, monthly_price_fen=3900, annual_price_fen=39900, monthly_credits=6000, signup_credits=0, rollover_cycles=3, recharge_bonus_bps=0, generation_concurrency=2, storage_bytes=50 * 1024**3, seat_limit=1, queue_priority=6, model_access_level="standard", max_video_resolution="1080p", max_image_resolution="2k", watermark_required=False, commercial_use=True, api_access=False, batch_access=False, rollover_policy="three_cycles", metadata_json=EMPTY_JSON),
            dict(id="planv-v1-pro", catalog_version_id="catalog-v1", plan_code="pro", membership_id="membership-pro", display_name="Pro", rank=2, monthly_price_fen=9900, annual_price_fen=99900, monthly_credits=18000, signup_credits=0, rollover_cycles=3, recharge_bonus_bps=700, generation_concurrency=4, storage_bytes=200 * 1024**3, seat_limit=1, queue_priority=4, model_access_level="advanced", max_video_resolution="1080p", max_image_resolution="4k", watermark_required=False, commercial_use=True, api_access=False, batch_access=False, rollover_policy="three_cycles", metadata_json=EMPTY_JSON),
            dict(id="planv-v1-studio", catalog_version_id="catalog-v1", plan_code="studio", membership_id="membership-studio", display_name="Studio", rank=3, monthly_price_fen=29900, annual_price_fen=319900, monthly_credits=55000, signup_credits=0, rollover_cycles=3, recharge_bonus_bps=1500, generation_concurrency=8, storage_bytes=1000 * 1024**3, seat_limit=3, queue_priority=2, model_access_level="advanced", max_video_resolution="1080p", max_image_resolution="4k", watermark_required=False, commercial_use=True, api_access=True, batch_access=True, rollover_policy="three_cycles", metadata_json=EMPTY_JSON),
            dict(id="planv-v1-team", catalog_version_id="catalog-v1", plan_code="team", membership_id="membership-team", display_name="Team", rank=4, monthly_price_fen=69900, annual_price_fen=749900, monthly_credits=130000, signup_credits=0, rollover_cycles=3, recharge_bonus_bps=2500, generation_concurrency=16, storage_bytes=2000 * 1024**3, seat_limit=5, queue_priority=0, model_access_level="advanced", max_video_resolution="1080p", max_image_resolution="4k", watermark_required=False, commercial_use=True, api_access=True, batch_access=True, rollover_policy="three_cycles", metadata_json=EMPTY_JSON),
        ],
        multiinsert=False,
    )

    package_rows = sa.table(
        "credit_packages", sa.column("id", sa.String), sa.column("catalog_version_id", sa.String), sa.column("package_code", sa.String),
        sa.column("display_name", sa.String), sa.column("price_fen", sa.Integer), sa.column("base_credits", sa.Integer),
        sa.column("package_bonus_bps", sa.Integer), sa.column("sort_order", sa.Integer), sa.column("active", sa.Boolean), sa.column("metadata_json", sa.JSON),
    )
    op.bulk_insert(package_rows, [
        dict(id="creditpkg-v1-10", catalog_version_id="catalog-v1", package_code="topup_10", display_name="¥10 积分包", price_fen=1000, base_credits=1000, package_bonus_bps=0, sort_order=10, active=True, metadata_json=EMPTY_JSON),
        dict(id="creditpkg-v1-50", catalog_version_id="catalog-v1", package_code="topup_50", display_name="¥50 积分包", price_fen=5000, base_credits=5000, package_bonus_bps=200, sort_order=20, active=True, metadata_json=EMPTY_JSON),
        dict(id="creditpkg-v1-100", catalog_version_id="catalog-v1", package_code="topup_100", display_name="¥100 积分包", price_fen=10000, base_credits=10000, package_bonus_bps=400, sort_order=30, active=True, metadata_json=EMPTY_JSON),
        dict(id="creditpkg-v1-300", catalog_version_id="catalog-v1", package_code="topup_300", display_name="¥300 积分包", price_fen=30000, base_credits=30000, package_bonus_bps=600, sort_order=40, active=True, metadata_json=EMPTY_JSON),
        dict(id="creditpkg-v1-500", catalog_version_id="catalog-v1", package_code="topup_500", display_name="¥500 积分包", price_fen=50000, base_credits=50000, package_bonus_bps=800, sort_order=50, active=True, metadata_json=EMPTY_JSON),
        dict(id="creditpkg-v1-1000", catalog_version_id="catalog-v1", package_code="topup_1000", display_name="¥1000 积分包", price_fen=100000, base_credits=100000, package_bonus_bps=1000, sort_order=60, active=True, metadata_json=EMPTY_JSON),
    ], multiinsert=False)

    sku_rows = sa.table(
        "billable_skus", sa.column("id", sa.String), sa.column("catalog_version_id", sa.String), sa.column("sku", sa.String),
        sa.column("display_name", sa.String), sa.column("category", sa.String), sa.column("unit", sa.String), sa.column("minimum_quantity", sa.Integer),
        sa.column("rounding_mode", sa.String), sa.column("access_level", sa.String), sa.column("active", sa.Boolean), sa.column("metadata_json", sa.JSON),
    )
    skus = [
        ("script.standard", "标准脚本生成", "text", "request", 1, "ceil", "standard", {}),
        ("storyboard.standard", "标准分镜拆解", "text", "request", 1, "ceil", "standard", {}),
        ("image.fast.1k", "Fast Image 1K", "image", "image", 1, "ceil", "basic", {}),
        ("image.standard.2k", "Standard Image 2K", "image", "image", 1, "ceil", "standard", {}),
        ("image.pro.2k", "Pro Image 2K", "image", "image", 1, "ceil", "advanced", {}),
        ("image.pro.4k", "Pro Image 4K", "image", "image", 1, "ceil", "advanced", {}),
        ("video.fast.720p", "Fast Video 720p", "video", "output_second", 1, "ceil", "basic", {}),
        ("video.standard.720p", "Standard Video 720p", "video", "output_second", 1, "ceil", "standard", {}),
        ("video.standard.1080p", "Standard Video 1080p", "video", "output_second", 1, "ceil", "standard", {}),
        ("video.premium.1080p", "Premium Video 1080p", "video", "output_second", 1, "ceil", "advanced", {}),
        ("video.premium.2k", "Premium Video 2K", "video", "output_second", 1, "ceil", "advanced", {}),
        ("video.retake.720p", "局部重拍 720p", "video_edit", "affected_second", 1, "ceil", "standard", {}),
        ("video.retake.1080p", "局部重拍 1080p", "video_edit", "affected_second", 1, "ceil", "standard", {}),
        ("video.extend.720p", "视频延长 720p", "video_edit", "added_second", 1, "ceil", "standard", {}),
        ("video.extend.1080p", "视频延长 1080p", "video_edit", "added_second", 1, "ceil", "standard", {}),
        ("tts.standard", "标准 TTS", "audio", "output_minute", 1, "ceil", "standard", {}),
        ("tts.pro", "高质量配音", "audio", "output_minute", 1, "ceil", "advanced", {}),
        ("music.standard", "音乐/BGM", "audio", "output_minute", 1, "ceil", "standard", {}),
    ];
    op.bulk_insert(sku_rows, [dict(id="sku-v1-" + sku.replace(".", "-"), catalog_version_id="catalog-v1", sku=sku, display_name=name, category=category, unit=unit, minimum_quantity=minimum, rounding_mode=rounding, access_level=access, active=True, metadata_json=EMPTY_JSON) for sku, name, category, unit, minimum, rounding, access, metadata in skus], multiinsert=False)

    rate_rows = sa.table(
        "rate_card_entries", sa.column("id", sa.String), sa.column("catalog_version_id", sa.String), sa.column("sku_id", sa.String),
        sa.column("credits_per_unit", sa.Integer), sa.column("minimum_credits", sa.Integer), sa.column("allowed_plan_codes", sa.JSON),
        sa.column("included_in_pass", sa.Boolean), sa.column("metadata_json", sa.JSON),
    )
    rates = {
        "script.standard": 20, "storyboard.standard": 40, "image.fast.1k": 20, "image.standard.2k": 50,
        "image.pro.2k": 100, "image.pro.4k": 160, "video.fast.720p": 60, "video.standard.720p": 100,
        "video.standard.1080p": 150, "video.premium.1080p": 250, "video.premium.2k": 400,
        "video.retake.720p": 90, "video.retake.1080p": 135, "video.extend.720p": 100, "video.extend.1080p": 150,
        "tts.standard": 30, "tts.pro": 80, "music.standard": 120,
    }
    # Free 方案的核心权益包含基础脚本/分镜，因此这两个文本 SKU
    # 即使 access_level=standard 也允许 Free 使用；图片/视频的
    # standard/advanced 档位仍按会员等级限制。
    access_by_level = {"basic": ["free", "creator", "pro", "studio", "team"], "standard": ["creator", "pro", "studio", "team"], "advanced": ["pro", "studio", "team"]}
    text_skus = {"script.standard", "storyboard.standard"}
    op.bulk_insert(rate_rows, [dict(id="rate-v1-" + sku.replace(".", "-"), catalog_version_id="catalog-v1", sku_id="sku-v1-" + sku.replace(".", "-"), credits_per_unit=credits, minimum_credits=0, allowed_plan_codes=["free", "creator", "pro", "studio", "team"] if sku in text_skus else access_by_level[next(access for key, _, _, _, _, _, access, _ in skus if key == sku)], included_in_pass=False, metadata_json=EMPTY_JSON) for sku, credits in rates.items()], multiinsert=False)


def downgrade() -> None:
    for table in ("credit_ledger", "credit_hold_items", "credit_holds", "billing_quote_lines", "billing_quotes", "credit_lots", "billing_accounts", "pass_products", "rate_card_entries", "billable_skus", "credit_packages", "billing_plan_versions"):
        op.drop_table(table)
    op.drop_index("ix_billing_catalog_versions_status_effective", table_name="billing_catalog_versions")
    op.drop_table("billing_catalog_versions")
