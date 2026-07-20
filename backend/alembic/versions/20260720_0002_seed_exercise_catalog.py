"""Seed the exercise catalog with common movements

Revision ID: 0002_seed_exercise_catalog
Revises: 0001_initial_schema
Create Date: 2026-07-20

The catalog is *reference data*, not user data: the app is unusable with an empty
`exercises` table, since nothing can be logged without a movement to point at. So
it ships as a migration rather than an ad-hoc script — every environment
(local, staging, production, a teammate's laptop) gets the identical catalog by
running the same `alembic upgrade head`, and it is versioned and reversible like
any other schema change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_seed_exercise_catalog"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A minimal ad-hoc table for the insert. We deliberately do NOT import the ORM
# model: a migration must keep working years from now, against the schema as it
# was at this revision. Importing `app.models.Exercise` would couple this file to
# whatever the model looks like *today*, and the migration would break the moment
# a column is added.
exercises_table = sa.table(
    "exercises",
    sa.column("name", sa.String),
    sa.column("primary_muscle_group", sa.Enum(name="muscle_group")),
    sa.column("equipment", sa.Enum(name="equipment")),
    sa.column("is_compound", sa.Boolean),
)

# `id`, `created_at`, `updated_at` are omitted on purpose — the server-side
# defaults (gen_random_uuid(), now()) fill them in.
SEED_EXERCISES = [
    # --- Barbell compounds ---
    ("Barbell Back Squat", "quads", "barbell", True),
    ("Barbell Front Squat", "quads", "barbell", True),
    ("Barbell Bench Press", "chest", "barbell", True),
    ("Barbell Incline Bench Press", "chest", "barbell", True),
    ("Barbell Deadlift", "hamstrings", "barbell", True),
    ("Barbell Romanian Deadlift", "hamstrings", "barbell", True),
    ("Barbell Overhead Press", "shoulders", "barbell", True),
    ("Barbell Row", "back", "barbell", True),
    ("Barbell Hip Thrust", "glutes", "barbell", True),
    # --- Dumbbell ---
    ("Dumbbell Bench Press", "chest", "dumbbell", True),
    ("Dumbbell Shoulder Press", "shoulders", "dumbbell", True),
    ("Dumbbell Row", "back", "dumbbell", True),
    ("Dumbbell Lateral Raise", "shoulders", "dumbbell", False),
    ("Dumbbell Bicep Curl", "biceps", "dumbbell", False),
    ("Dumbbell Lunge", "quads", "dumbbell", True),
    # --- Bodyweight ---
    ("Pull-Up", "back", "bodyweight", True),
    ("Chin-Up", "biceps", "bodyweight", True),
    ("Push-Up", "chest", "bodyweight", True),
    ("Dip", "triceps", "bodyweight", True),
    ("Plank", "core", "bodyweight", False),
    ("Hanging Leg Raise", "core", "bodyweight", False),
    # --- Machine / cable ---
    ("Lat Pulldown", "back", "cable", True),
    ("Seated Cable Row", "back", "cable", True),
    ("Leg Press", "quads", "machine", True),
    ("Leg Curl", "hamstrings", "machine", False),
    ("Leg Extension", "quads", "machine", False),
    ("Calf Raise", "calves", "machine", False),
    ("Cable Tricep Pushdown", "triceps", "cable", False),
    ("Cable Chest Fly", "chest", "cable", False),
    ("Face Pull", "shoulders", "cable", False),
    # --- Other ---
    ("Kettlebell Swing", "glutes", "kettlebell", True),
    ("Farmer's Carry", "forearms", "other", True),
]


def upgrade() -> None:
    op.bulk_insert(
        exercises_table,
        [
            {
                "name": name,
                "primary_muscle_group": muscle,
                "equipment": equipment,
                "is_compound": is_compound,
            }
            for name, muscle, equipment, is_compound in SEED_EXERCISES
        ],
    )


def downgrade() -> None:
    # Delete by name rather than truncating: a user may have added custom
    # movements in a later phase, and a downgrade of *this* revision should
    # remove only what *this* revision inserted.
    #
    # Note this will fail loudly if any workout_exercises row still references a
    # seeded exercise — that is the ON DELETE RESTRICT from revision 0001 doing
    # its job. Refusing to silently destroy training history is the correct
    # behaviour; clear the dependent data first if you really mean it.
    op.execute(
        exercises_table.delete().where(
            exercises_table.c.name.in_([name for name, _, _, _ in SEED_EXERCISES])
        )
    )
