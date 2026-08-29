"""新增可并存的邮箱、手机号和微信登录身份。

Revision ID: 027_user_identities
Revises: 026_unified_narration_cues
"""

from alembic import op
import sqlalchemy as sa


revision = "027_user_identities"
down_revision = "026_unified_narration_cues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("provider_app_id", sa.String(length=255), nullable=True),
        sa.Column("provider_openid", sa.String(length=255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "identifier", name="uq_user_identity_provider_identifier"
        ),
    )
    op.create_index("ix_user_identities_provider", "user_identities", ["provider"])
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    # 兼容旧结构：普通邮箱保留密码；手机号和微信伪邮箱转换为独立身份。
    op.execute(
        """
        INSERT INTO user_identities (
            id, user_id, provider, identifier, password_hash,
            provider_app_id, provider_openid, verified_at,
            last_login_at, created_at, updated_at
        )
        SELECT
            'identity-' || substr(md5(id || ':' || email), 1, 12),
            id,
            CASE
                WHEN email ~ '^[0-9]{11}@openvma\\.cn$' THEN 'phone'
                WHEN email LIKE 'wx\\_%@openvma.cn' ESCAPE '\\' THEN 'wechat'
                ELSE 'email'
            END,
            CASE
                WHEN email ~ '^[0-9]{11}@openvma\\.cn$'
                    THEN '+86' || split_part(email, '@', 1)
                WHEN email LIKE 'wx\\_%@openvma.cn' ESCAPE '\\'
                    THEN 'openid:legacy:' || substr(split_part(email, '@', 1), 4)
                ELSE lower(email)
            END,
            CASE
                WHEN email ~ '^[0-9]{11}@openvma\\.cn$'
                  OR email LIKE 'wx\\_%@openvma.cn' ESCAPE '\\'
                    THEN NULL
                ELSE password_hash
            END,
            NULL,
            CASE
                WHEN email LIKE 'wx\\_%@openvma.cn' ESCAPE '\\'
                    THEN substr(split_part(email, '@', 1), 4)
                ELSE NULL
            END,
            created_at,
            NULL,
            created_at,
            updated_at
        FROM users
        ON CONFLICT (provider, identifier) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_index("ix_user_identities_provider", table_name="user_identities")
    op.drop_table("user_identities")
