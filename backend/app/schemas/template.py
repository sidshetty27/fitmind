"""Workout template schemas.

Mirrors `schemas/workout.py`: the client sends `exercise_id` plus the prescribed
numbers and never sends `position`, which the server assigns from array order.
Same rule, same reason — it makes the `(template_id, position)` uniqueness
constraint impossible to violate from the API.

`TemplateApply` is the one shape with no workout equivalent: it carries the small
set of facts a template cannot know (which day this session happened, how long it
took) so the server can turn a plan into a logged workout in one call.
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


class TemplateExerciseCreate(BaseModel):
    """One prescribed movement, on input. `position` is server-assigned."""

    exercise_id: uuid.UUID
    sets: PositiveInt
    reps: PositiveInt
    weight_kg: NonNegativeWeight | None = None
    rpe: Rpe | None = None
    notes: str | None = None


class TemplateExerciseRead(ORMModel):
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise: ExerciseRead
    position: int
    sets: int
    reps: int
    weight_kg: Decimal | None
    rpe: Decimal | None
    notes: str | None


class TemplateCreate(BaseModel):
    # Required, unlike a workout's title: templates are picked from a list by name.
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    exercises: list[TemplateExerciseCreate] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    """Partial update of a template's own fields (not its exercise list).

    Same split as workouts: replacing the exercise list is the separate, explicit
    `PUT /templates/{id}/exercises`, so renaming a plan can never wipe it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class TemplateExercisesReplace(BaseModel):
    exercises: list[TemplateExerciseCreate]


class TemplateRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    exercises: list[TemplateExerciseRead]


class TemplateListItem(ORMModel):
    """Lightweight list row: a count instead of the nested exercises."""

    id: uuid.UUID
    name: str
    description: str | None
    exercise_count: int
    created_at: datetime
    updated_at: datetime


class TemplateApply(BaseModel):
    """Turn a template into a logged workout.

    Everything here is what the plan cannot know: the day it was actually
    performed, how long it took, and any notes about this specific session. The
    movements come from the template.

    The resulting workout is an independent copy — editing the template afterwards
    does not reach back and rewrite a session that already happened.
    """

    performed_on: date
    # Defaults to the template's name when omitted, which is almost always what
    # the user means by "log my Push Day A".
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    duration_min: PositiveInt | None = None
