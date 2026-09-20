"""Align seeded V2 data with the Excel commercial rules.

Revision ID: 037_billing_v2_rule_alignment
Revises: 036_order_billing_v2_snapshot
"""

from collections.abc import Sequence

from alembic import op


revision: str = "037_billing_v2_rule_alignment"
down_revision: str | None = "036_order_billing_v2_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 034 seeds these values for fresh installs. This repeatable alignment is
    # needed when a database has already applied 034–036 before the rule fix.
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
        UPDATE rate_card_entries AS rate
        SET allowed_plan_codes = '["free", "creator", "pro", "studio", "team"]'::json
        FROM billable_skus AS sku
        WHERE rate.sku_id = sku.id
          AND sku.catalog_version_id = rate.catalog_version_id
          AND sku.sku IN ('script.standard', 'storyboard.standard')
        """
    )


def downgrade() -> None:
    # The alignment is data-only and must not attempt to reconstruct arbitrary
    # administrator edits made after publication.
    pass

