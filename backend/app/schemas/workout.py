"""Workout schemas, including the nested exercise entries.

The write/read split is deliberate:
  - On write, a client sends `exercise_id` (a reference into the shared catalog)
    plus the performance data. It does NOT send `position` — the server assigns
    positions from array order, which is what guarantees the
    `(workout_id, position)` uniqueness the schema requires without making every
    client manage slot numbers.
  - On read, each entry echoes its `position` and embeds the full `exercise` so a
    client can render "Barbell Bench Press — 3×8 @ 60kg" without a second lookup.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import (
    NonNegativeWeight,
    ORMModel,
    PositiveInt,
    Rpe,
)
from app.schemas.exercise import ExerciseRead


class WorkoutExerciseCreate(BaseModel):
    """One movement as performed, on input. `position` is server-assigned."""

    exercise_id: uuid.UUID
    sets: PositiveInt
    reps: PositiveInt
    # Nullable: bodyweight movements have no external load. 0 would be a lie that
    # skews volume averages; the DB stores NULL and aggregates skip it.
    weight_kg: NonNegativeWeight | None = None
    rpe: Rpe | None = None
    notes: str | None = None


class WorkoutExerciseRead(ORMModel):
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise: ExerciseRead
    position: int
    sets: int
    reps: int
    weight_kg: Decimal | None
    rpe: Decimal | None
    notes: str | None


class WorkoutCreate(BaseModel):
    performed_on: date
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    duration_min: PositiveInt | None = None
    # Exercises are optional at creation: logging the session first and adding
    # movements after is a normal flow.
    exercises: list[WorkoutExerciseCreate] = Field(default_factory=list)


class WorkoutUpdate(BaseModel):
    """Partial update of a workout's own fields (not its exercise list).

    Replacing the exercise list is a separate, explicit operation
    (`PUT /workouts/{id}/exercises`) so a title edit can never accidentally wipe a
    session's logged sets.
    """

    performed_on: date | None = None
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    duration_min: PositiveInt | None = None


class WorkoutExercisesReplace(BaseModel):
    """Full replacement of a workout's exercise list — atomic set-the-whole-thing."""

    exercises: list[WorkoutExerciseCreate]


class WorkoutRead(ORMModel):
    id: uuid.UUID
    performed_on: date
    title: str | None
    notes: str | None
    duration_min: int | None
    created_at: datetime
    updated_at: datetime
    exercises: list[WorkoutExerciseRead]


class WorkoutListItem(ORMModel):
    """Lightweight list row: no nested exercises, just a count.

    The list view renders a calendar/table; embedding every set of every workout
    would balloon the payload for data the row does not show. `exercise_count`
    comes from an aggregate in the query, not from loading the children.
    """

    id: uuid.UUID
    performed_on: date
    title: str | None
    duration_min: int | None
    exercise_count: int
    created_at: datetime
    updated_at: datetime
