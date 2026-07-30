"""ai_analyses — stored AI coach runs

Revision ID: 0004_ai_analyses
Revises: 0003_workout_templates
Create Date: 2026-07-29

Purely additive: one new table and its index. Nothing existing is altered, so
this is safe to apply to a live database.

Autogenerate also proposed dropping the server default on `exercises.is_compound`,
which is pre-existing drift between the model and the database and has nothing to
do with this change. It is deliberately left out — a migration named for one thing
should not quietly do another, and dropping a default on a live table deserves its
own reviewed change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_ai_analyses"
down_revision: str | None = "0003_workout_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_analyses",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("workout_count", sa.Integer(), nullable=False),
        sa.Column(
            "findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
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
            "(narrative IS NULL) = (model IS NULL)",
            name=op.f("ck_ai_analyses_narrative_model_together"),
        ),
        sa.CheckConstraint(
            "window_end >= window_start", name=op.f("ck_ai_analyses_window_ordered")
        ),
        sa.CheckConstraint(
            "workout_count >= 0", name=op.f("ck_ai_analyses_workout_count_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_analyses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_analyses")),
    )
    op.create_index(
        "ix_ai_analyses_user_id_created_at",
        "ai_analyses",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_analyses_user_id_created_at", table_name="ai_analyses")
    op.drop_table("ai_analyses")
