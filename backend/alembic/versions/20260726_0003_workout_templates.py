"""Phase 5: workout templates — reusable session plans

Revision ID: 0003_workout_templates
Revises: 0002_seed_exercise_catalog
Create Date: 2026-07-26

Adds `workout_templates` and `workout_template_exercises`. Purely additive: no
existing table, column, or constraint is touched, so this is safe to apply to a
database with live data and the downgrade is a clean drop.

The two tables mirror `workouts` / `workout_exercises` in shape, which is what
lets "apply this template" be a field-for-field copy rather than a translation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_workout_templates"
down_revision: str | None = "0002_seed_exercise_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        # Constraints are left unnamed wherever the models leave them unnamed, so
        # `NAMING_CONVENTION` derives identical names on both sides. Naming one
        # side by hand is what produces phantom autogenerate drift forever.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # A user cannot own two templates with the same name — a picker showing
        # "Push Day A" twice is indistinguishable to the person choosing.
        sa.UniqueConstraint("user_id", "name", name="uq_workout_templates_user_id_name"),
    )
    op.create_index(
        "ix_workout_templates_user_id", "workout_templates", ["user_id"], unique=False
    )

    op.create_table(
        "workout_template_exercises",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("rpe", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["workout_templates.id"], ondelete="CASCADE"
        ),
        # RESTRICT: the exercise catalog is shared reference data. Deleting a
        # movement must not silently gut every user's saved plans.
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "template_id",
            "position",
            name="uq_workout_template_exercises_template_id_position",
        ),
        # Mirrors the CHECKs on `workout_exercises`. Stated in the database, not
        # only in Pydantic, because the API is not the only thing that will ever
        # write here.
        sa.CheckConstraint("sets > 0", name="sets_positive"),
        sa.CheckConstraint("reps > 0", name="reps_positive"),
        sa.CheckConstraint("position >= 0", name="position_non_negative"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg >= 0", name="weight_non_negative"
        ),
        sa.CheckConstraint(
            "rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"
        ),
    )
    op.create_index(
        "ix_workout_template_exercises_template_id",
        "workout_template_exercises",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        "ix_workout_template_exercises_exercise_id",
        "workout_template_exercises",
        ["exercise_id"],
        unique=False,
    )


def downgrade() -> None:
    # Children before parents, mirroring 0001's ordering.
    op.drop_index(
        "ix_workout_template_exercises_exercise_id",
        table_name="workout_template_exercises",
    )
    op.drop_index(
        "ix_workout_template_exercises_template_id",
        table_name="workout_template_exercises",
    )
    op.drop_table("workout_template_exercises")
    op.drop_index("ix_workout_templates_user_id", table_name="workout_templates")
    op.drop_table("workout_templates")
