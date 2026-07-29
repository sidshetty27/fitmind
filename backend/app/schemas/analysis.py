"""Shapes for derived training data.

Unlike the rest of this package these do not mirror a table — nothing here is
stored. They are the contract for computed output, shared by two very different
consumers: the Progress charts (which need series) and the AI layer (which needs
a compact, already-summarised view it can put in a prompt without shipping every
row it ever logged).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import NonNegativeInt


class ExerciseSessionPoint(BaseModel):
    """One movement as performed in one session — a single point on a series."""

    workout_id: uuid.UUID
    performed_on: date
    sets: NonNegativeInt
    reps: NonNegativeInt
    weight_kg: Decimal | None = None
    rpe: Decimal | None = None
    # Derived. `None` means "not applicable" (bodyweight), never zero — see
    # `app.analysis.metrics`.
    volume_kg: Decimal | None = None
    estimated_one_rm: Decimal | None = None
    total_reps: NonNegativeInt


class ExerciseHistory(BaseModel):
    """Every logged instance of one movement, oldest first, plus its trend."""

    exercise_id: uuid.UUID
    exercise_name: str
    points: list[ExerciseSessionPoint] = Field(default_factory=list)

    session_count: NonNegativeInt
    best_estimated_one_rm: Decimal | None = None
    # Change in best-estimated-1RM from the first session in the window to the
    # last. Signed: negative is a real finding, not an error.
    one_rm_change_pct: Decimal | None = None


class WeekVolume(BaseModel):
    """Training load for one ISO week.

    `volume_kg` covers loaded work only, so `total_reps` is reported beside it
    rather than folded in — a week of dips and pull-ups has real training stress
    and zero volume load, and a chart showing only the former would call that
    week empty.
    """

    week_start: date
    volume_kg: Decimal
    total_reps: NonNegativeInt
    session_count: NonNegativeInt


class PersonalRecord(BaseModel):
    """The best a user has ever done on one movement, and when.

    Three records rather than one because they answer different questions and can
    land in different sessions: the heaviest bar loaded, the best estimated max
    (which a rep PR can set without touching the heaviest weight), and the biggest
    single session of work. Each carries its own date — a PR board whose entries
    all shared one date would be describing a session, not a record.

    Every field is optional for the same reason `metrics` returns `None`: a
    bodyweight-only movement has no weight or 1RM record, but it still has a
    session count and a last-performed date worth showing.
    """

    exercise_id: uuid.UUID
    exercise_name: str

    heaviest_weight_kg: Decimal | None = None
    heaviest_weight_on: date | None = None

    best_estimated_one_rm: Decimal | None = None
    best_estimated_one_rm_on: date | None = None

    best_session_volume_kg: Decimal | None = None
    best_session_volume_on: date | None = None

    session_count: NonNegativeInt
    last_performed_on: date


class TrainingSummary(BaseModel):
    """The whole aggregation layer's output for one user over one window.

    This is the object the AI layer is meant to consume — bounded in size by the
    window and the per-exercise cap, so a prompt built from it does not grow with
    the user's training history.
    """

    window_start: date
    window_end: date
    workout_count: NonNegativeInt
    weekly_volume: list[WeekVolume] = Field(default_factory=list)
    exercises: list[ExerciseHistory] = Field(default_factory=list)


__all__ = [
    "ExerciseHistory",
    "ExerciseSessionPoint",
    "PersonalRecord",
    "TrainingSummary",
    "WeekVolume",
]
