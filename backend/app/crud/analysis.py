"""Training-history aggregation — always scoped to the owning user.

Same ownership rule as every other module here: the `user_id` predicate is on the
query, so there is no path that reads another user's training. These are all
reads; nothing in this module writes.

The queries are deliberately *flat* — one join across workouts, entries, and the
catalog, ordered by date — and the shaping into series happens in Python. A
single indexed scan of one user's rows is cheap, and the derived numbers
(1RM, volume, percent change) come from `app.analysis.metrics`, which is pure and
unit-tested without a database. Pushing that maths into SQL would move it
somewhere the default test suite cannot reach.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import metrics
from app.models.exercise import Exercise
from app.models.workout import Workout
from app.models.workout_exercise import WorkoutExercise
from app.schemas.analysis import (
    ExerciseHistory,
    ExerciseSessionPoint,
    TrainingSummary,
    WeekVolume,
)

# Keeps a summary bounded regardless of how much a user has logged, so a prompt
# built from it has a predictable ceiling. Ordered by session count, so the cut
# falls on movements the user rarely trains rather than their main lifts.
DEFAULT_EXERCISE_LIMIT = 12
DEFAULT_WINDOW_WEEKS = 12


def _week_start(day: date) -> date:
    """The Monday of `day`'s ISO week — the bucket key for weekly rollups."""
    return day - timedelta(days=day.weekday())


async def exercise_history(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    since: date | None = None,
    exercise_id: uuid.UUID | None = None,
    limit_exercises: int | None = DEFAULT_EXERCISE_LIMIT,
) -> list[ExerciseHistory]:
    """Per-movement series, oldest point first, most-trained movement first.

    Pass `exercise_id` to narrow to a single movement (the "how is my bench
    going" query); omit it for the full picture.
    """
    stmt = (
        select(
            WorkoutExercise.exercise_id,
            Exercise.name,
            Workout.id,
            Workout.performed_on,
            WorkoutExercise.sets,
            WorkoutExercise.reps,
            WorkoutExercise.weight_kg,
            WorkoutExercise.rpe,
        )
        .join(Workout, Workout.id == WorkoutExercise.workout_id)
        .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
        .where(Workout.user_id == user_id)
        .order_by(Workout.performed_on, WorkoutExercise.position)
    )
    if since is not None:
        stmt = stmt.where(Workout.performed_on >= since)
    if exercise_id is not None:
        stmt = stmt.where(WorkoutExercise.exercise_id == exercise_id)

    grouped: dict[uuid.UUID, list] = defaultdict(list)
    names: dict[uuid.UUID, str] = {}
    for row in (await db.execute(stmt)).all():
        ex_id, ex_name, workout_id, performed_on, sets, reps, weight, rpe = row
        names[ex_id] = ex_name
        grouped[ex_id].append(
            ExerciseSessionPoint(
                workout_id=workout_id,
                performed_on=performed_on,
                sets=sets,
                reps=reps,
                weight_kg=weight,
                rpe=rpe,
                volume_kg=metrics.entry_volume(sets, reps, weight),
                estimated_one_rm=metrics.estimate_one_rm(weight, reps),
                total_reps=metrics.total_reps(sets, reps),
            )
        )

    histories = [
        _build_history(ex_id, names[ex_id], points) for ex_id, points in grouped.items()
    ]
    # Most-trained first, then name so equal counts do not order arbitrarily
    # between calls — a jittering list is a bad chart legend and a bad diff.
    histories.sort(key=lambda h: (-h.session_count, h.exercise_name))
    if limit_exercises is not None:
        histories = histories[:limit_exercises]
    return histories


def _build_history(
    exercise_id: uuid.UUID, name: str, points: list[ExerciseSessionPoint]
) -> ExerciseHistory:
    """Turn one movement's ordered points into its trend summary.

    The change is measured between the *first and last points that actually have
    an estimate*, not the first and last points overall. A window that opens or
    closes on a bodyweight or high-rep set would otherwise report no trend at all
    for a movement that plainly has one.
    """
    with_estimate = [p for p in points if p.estimated_one_rm is not None]
    best = max((p.estimated_one_rm for p in with_estimate), default=None)
    change = (
        metrics.percent_change(
            with_estimate[0].estimated_one_rm, with_estimate[-1].estimated_one_rm
        )
        if len(with_estimate) >= 2
        else None
    )
    return ExerciseHistory(
        exercise_id=exercise_id,
        exercise_name=name,
        points=points,
        session_count=len({p.workout_id for p in points}),
        best_estimated_one_rm=best,
        one_rm_change_pct=change,
    )


async def weekly_volume(
    db: AsyncSession, *, user_id: uuid.UUID, since: date | None = None
) -> list[WeekVolume]:
    """Loaded volume, total reps, and session count per ISO week, oldest first.

    Weeks with no training are omitted rather than zero-filled — the caller knows
    the window and can fill gaps for a chart axis, whereas this layer inventing
    zero-rows would misreport "rested" as "logged nothing".
    """
    stmt = (
        select(
            Workout.performed_on,
            Workout.id,
            WorkoutExercise.sets,
            WorkoutExercise.reps,
            WorkoutExercise.weight_kg,
        )
        .join(WorkoutExercise, Workout.id == WorkoutExercise.workout_id)
        .where(Workout.user_id == user_id)
        .order_by(Workout.performed_on)
    )
    if since is not None:
        stmt = stmt.where(Workout.performed_on >= since)

    volume: dict[date, Decimal] = defaultdict(lambda: Decimal("0.00"))
    reps: dict[date, int] = defaultdict(int)
    sessions: dict[date, set[uuid.UUID]] = defaultdict(set)

    for performed_on, workout_id, sets, set_reps, weight in (await db.execute(stmt)).all():
        bucket = _week_start(performed_on)
        entry = metrics.entry_volume(sets, set_reps, weight)
        if entry is not None:
            volume[bucket] += entry
        reps[bucket] += metrics.total_reps(sets, set_reps)
        sessions[bucket].add(workout_id)

    return [
        WeekVolume(
            week_start=bucket,
            volume_kg=volume[bucket],
            total_reps=reps[bucket],
            session_count=len(sessions[bucket]),
        )
        for bucket in sorted(sessions)
    ]


async def training_summary(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    today: date,
    weeks: int = DEFAULT_WINDOW_WEEKS,
    limit_exercises: int | None = DEFAULT_EXERCISE_LIMIT,
) -> TrainingSummary:
    """The bounded view of a user's recent training.

    `today` is a parameter rather than a `date.today()` call so the window is
    reproducible in tests and identical across a request that straddles midnight.
    """
    window_start = _week_start(today) - timedelta(weeks=weeks - 1)

    count_stmt = select(func.count(Workout.id)).where(
        Workout.user_id == user_id,
        Workout.performed_on >= window_start,
        Workout.performed_on <= today,
    )
    workout_count = (await db.execute(count_stmt)).scalar_one()

    return TrainingSummary(
        window_start=window_start,
        window_end=today,
        workout_count=workout_count,
        weekly_volume=await weekly_volume(db, user_id=user_id, since=window_start),
        exercises=await exercise_history(
            db, user_id=user_id, since=window_start, limit_exercises=limit_exercises
        ),
    )


__all__ = [
    "DEFAULT_EXERCISE_LIMIT",
    "DEFAULT_WINDOW_WEEKS",
    "exercise_history",
    "training_summary",
    "weekly_volume",
]
