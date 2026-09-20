"""Versioned commercial catalog and V-Credits wallet models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BillingCatalogVersion(Base):
    """An immutable, publishable commercial configuration version."""

    __tablename__ = "billing_catalog_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_billing_catalog_versions_status",
        ),
        UniqueConstraint("version_key", name="uq_billing_catalog_versions_key"),
        Index("ix_billing_catalog_versions_status_effective", "status", "effective_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"catalog-{uuid.uuid4().hex[:16]}"
    )
    version_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_admin_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_admin_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    plans: Mapped[list["BillingPlanVersion"]] = relationship(
        "BillingPlanVersion", back_populates="catalog", cascade="all, delete-orphan"
    )
    credit_packages: Mapped[list["CreditPackage"]] = relationship(
        "CreditPackage", back_populates="catalog", cascade="all, delete-orphan"
    )
    skus: Mapped[list["BillableSku"]] = relationship(
        "BillableSku", back_populates="catalog", cascade="all, delete-orphan"
    )
    rate_entries: Mapped[list["RateCardEntry"]] = relationship(
        "RateCardEntry", back_populates="catalog", cascade="all, delete-orphan"
    )
    passes: Mapped[list["PassProduct"]] = relationship(
        "PassProduct", back_populates="catalog", cascade="all, delete-orphan"
    )


class BillingPlanVersion(Base):
    """A plan's price and entitlement snapshot inside one catalog version."""

    __tablename__ = "billing_plan_versions"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "plan_code", name="uq_billing_plan_versions_code"),
        CheckConstraint("monthly_price_fen >= 0", name="ck_billing_plan_versions_monthly_price"),
        CheckConstraint("annual_price_fen IS NULL OR annual_price_fen >= 0", name="ck_billing_plan_versions_annual_price"),
        CheckConstraint("monthly_credits >= 0", name="ck_billing_plan_versions_monthly_credits"),
        CheckConstraint("signup_credits >= 0", name="ck_billing_plan_versions_signup_credits"),
        CheckConstraint("recharge_bonus_bps >= 0", name="ck_billing_plan_versions_bonus"),
        CheckConstraint("generation_concurrency >= 1", name="ck_billing_plan_versions_concurrency"),
        CheckConstraint("storage_bytes >= 0", name="ck_billing_plan_versions_storage"),
        CheckConstraint("seat_limit >= 1", name="ck_billing_plan_versions_seats"),
        Index("ix_billing_plan_versions_catalog_rank", "catalog_version_id", "rank"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"planv-{uuid.uuid4().hex[:16]}"
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    membership_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_price_fen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    annual_price_fen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    signup_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rollover_cycles: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    recharge_bonus_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    seat_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    queue_priority: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    model_access_level: Mapped[str] = mapped_column(String(50), default="basic", nullable=False)
    max_video_resolution: Mapped[str] = mapped_column(String(20), default="720p", nullable=False)
    max_image_resolution: Mapped[str] = mapped_column(String(20), default="1k", nullable=False)
    watermark_required: Mapped[bool] = mapped_column(default=True, nullable=False)
    commercial_use: Mapped[bool] = mapped_column(default=False, nullable=False)
    api_access: Mapped[bool] = mapped_column(default=False, nullable=False)
    batch_access: Mapped[bool] = mapped_column(default=False, nullable=False)
    rollover_policy: Mapped[str] = mapped_column(String(50), default="three_cycles", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    catalog: Mapped["BillingCatalogVersion"] = relationship("BillingCatalogVersion", back_populates="plans")


class CreditPackage(Base):
    """Top-up package with package bonus; membership bonus is applied at checkout."""

    __tablename__ = "credit_packages"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "package_code", name="uq_credit_packages_code"),
        CheckConstraint("price_fen > 0", name="ck_credit_packages_price"),
        CheckConstraint("base_credits > 0", name="ck_credit_packages_credits"),
        CheckConstraint("package_bonus_bps >= 0", name="ck_credit_packages_bonus"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"creditpkg-{uuid.uuid4().hex[:16]}"
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    package_code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    base_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    package_bonus_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    catalog: Mapped["BillingCatalogVersion"] = relationship("BillingCatalogVersion", back_populates="credit_packages")


class BillableSku(Base):
    """A stable user-facing billable capability such as video.standard.1080p."""

    __tablename__ = "billable_skus"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "sku", name="uq_billable_skus_sku"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"sku-{uuid.uuid4().hex[:16]}"
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    minimum_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(30), default="ceil", nullable=False)
    access_level: Mapped[str] = mapped_column(String(50), default="basic", nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    catalog: Mapped["BillingCatalogVersion"] = relationship("BillingCatalogVersion", back_populates="skus")


class RateCardEntry(Base):
    """Price in credits for one unit of a billable SKU."""

    __tablename__ = "rate_card_entries"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "sku_id", name="uq_rate_card_entries_sku"),
        CheckConstraint("credits_per_unit > 0", name="ck_rate_card_entries_positive"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"rate-{uuid.uuid4().hex[:16]}"
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billable_skus.id", ondelete="CASCADE"), nullable=False
    )
    credits_per_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allowed_plan_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    included_in_pass: Mapped[bool] = mapped_column(default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    catalog: Mapped["BillingCatalogVersion"] = relationship("BillingCatalogVersion", back_populates="rate_entries")
    sku: Mapped["BillableSku"] = relationship("BillableSku")


class PassProduct(Base):
    """Time-limited model pass / unlimited card."""

    __tablename__ = "pass_products"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "pass_code", name="uq_pass_products_code"),
        CheckConstraint("price_fen > 0", name="ck_pass_products_price"),
        CheckConstraint("duration_seconds > 0", name="ck_pass_products_duration"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"pass-{uuid.uuid4().hex[:16]}"
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    pass_code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    model_patterns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolution_limit: Mapped[str] = mapped_column(String(20), default="720p", nullable=False)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fair_use_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    catalog: Mapped["BillingCatalogVersion"] = relationship("BillingCatalogVersion", back_populates="passes")


class BillingAccount(Base):
    """Wallet owner. Users and future teams both use this abstraction."""

    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", name="uq_billing_accounts_owner"),
        CheckConstraint("owner_type IN ('user', 'team', 'enterprise')", name="ck_billing_accounts_owner_type"),
        CheckConstraint("cached_available_credits >= 0", name="ck_billing_accounts_available"),
        CheckConstraint("cached_reserved_credits >= 0", name="ck_billing_accounts_reserved"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"acct-{uuid.uuid4().hex[:16]}"
    )
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cached_available_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_reserved_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CreditLot(Base):
    """A grant batch with its own expiry and source provenance."""

    __tablename__ = "credit_lots"
    __table_args__ = (
        Index("ix_credit_lots_account_expiry", "billing_account_id", "expires_at"),
        CheckConstraint("original_amount > 0", name="ck_credit_lots_original_positive"),
        CheckConstraint("remaining_amount >= 0", name="ck_credit_lots_remaining_nonnegative"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"lot-{uuid.uuid4().hex[:16]}"
    )
    billing_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    catalog_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CreditLedger(Base):
    """Immutable wallet ledger entry.

    ``amount`` is the change to the economic balance (available + reserved),
    and ``balance_after`` records that total after the event. Reservations and
    releases therefore have zero amount; capture records the actual spend.
    """

    __tablename__ = "credit_ledger"
    __table_args__ = (
        Index("ix_credit_ledger_account_created", "billing_account_id", "created_at"),
        UniqueConstraint("billing_account_id", "idempotency_key", name="uq_credit_ledger_idempotency"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"ledger-{uuid.uuid4().hex[:16]}"
    )
    billing_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    credit_lot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("credit_lots.id", ondelete="SET NULL"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    quote_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("billing_quotes.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CreditHold(Base):
    """Credits reserved for a job before provider execution."""

    __tablename__ = "credit_holds"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_credit_holds_idempotency"),
        CheckConstraint("amount > 0", name="ck_credit_holds_positive"),
        CheckConstraint("status IN ('active', 'captured', 'released', 'expired')", name="ck_credit_holds_status"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"hold-{uuid.uuid4().hex[:16]}"
    )
    billing_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("billing_quotes.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CreditHoldItem(Base):
    """FIFO allocation from a hold to one or more credit lots."""

    __tablename__ = "credit_hold_items"
    __table_args__ = (
        UniqueConstraint("hold_id", "credit_lot_id", name="uq_credit_hold_items_lot"),
        CheckConstraint("amount > 0", name="ck_credit_hold_items_positive"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"holditem-{uuid.uuid4().hex[:16]}"
    )
    hold_id: Mapped[str] = mapped_column(String(64), ForeignKey("credit_holds.id", ondelete="CASCADE"), nullable=False)
    credit_lot_id: Mapped[str] = mapped_column(String(64), ForeignKey("credit_lots.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)


class BillingQuote(Base):
    """Short-lived backend-generated quote for a billable operation."""

    __tablename__ = "billing_quotes"
    __table_args__ = (
        CheckConstraint("total_credits > 0", name="ck_billing_quotes_positive"),
        CheckConstraint("status IN ('issued', 'consumed', 'expired', 'cancelled')", name="ck_billing_quotes_status"),
        Index("ix_billing_quotes_account_expires", "billing_account_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"quote-{uuid.uuid4().hex[:16]}"
    )
    billing_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    catalog_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_catalog_versions.id", ondelete="RESTRICT"), nullable=False
    )
    total_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="CREDITS", nullable=False)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="issued", nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class BillingQuoteLine(Base):
    """A single SKU line inside a quote."""

    __tablename__ = "billing_quote_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_billing_quote_lines_quantity"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"quoteline-{uuid.uuid4().hex[:16]}"
    )
    quote_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("billable_skus.id", ondelete="RESTRICT"), nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
