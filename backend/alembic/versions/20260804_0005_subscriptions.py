"""subscriptions — mirrored Stripe billing state

Revision ID: 0005_subscriptions
Revises: 0004_ai_analyses
Create Date: 2026-08-04

Purely additive: one new table, no index of its own (the three UNIQUE constraints
already back every lookup it serves). Nothing existing is altered, so this is safe
to apply to a live database.

Autogenerate again proposed dropping the server default on `exercises.is_compound`
— the same pre-existing model/database drift that `0004` documented and left
alone, and for the same reason: a migration named for one thing should not quietly
do another. It is still outstanding and still deserves its own reviewed change.

No data migration for existing users. Absence of a row is what "free tier" means
(see `models/subscription.py`), so every current account is already correct.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_subscriptions"
down_revision: str | None = "0004_ai_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("price_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(stripe_subscription_id IS NULL) = (status IS NULL)",
            name=op.f("ck_subscriptions_subscription_status_together"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        sa.UniqueConstraint(
            "stripe_customer_id", name="uq_subscriptions_stripe_customer_id"
        ),
        sa.UniqueConstraint(
            "stripe_subscription_id", name="uq_subscriptions_stripe_subscription_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
