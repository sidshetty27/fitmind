"""Workout data access — always scoped to the owning user.

**Ownership is enforced here, not hoped for in the route.** Every read and write
carries a `user_id` predicate, so there is no code path that returns or mutates
another user's workout. A missing/foreign id comes back as `None`, which the
router turns into a 404 (never a 403 — we do not confirm that someone else's
workout exists).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exercise import Exercise
from app.models.workout import Workout
from app.models.workout_exercise import WorkoutExercise
from app.schemas.workout import WorkoutCreate, WorkoutExercisesReplace, WorkoutUpdate


class UnknownExerciseError(Exception):
    """Raised when a workout references catalog ids that do not exist."""

    def __init__(self, ids: set[uuid.UUID]) -> None:
        self.ids = ids
        super().__init__(f"Unknown exercise ids: {sorted(str(i) for i in ids)}")


# The load rule for returning a fully-populated workout: its exercises (ordered by
# position via the relationship) each with their catalog entry. `selectinload`
# issues one extra SELECT per level instead of a row-multiplying JOIN, and avoids
# the N+1 that lazy loading would cause — which in async SQLAlchemy would not even
# be an N+1 but a MissingGreenlet crash.
_FULL_LOAD = selectinload(Workout.exercises).selectinload(WorkoutExercise.exercise)


async def _ensure_exercises_exist(
    db: AsyncSession, exercise_ids: list[uuid.UUID]
) -> None:
    """Validate catalog references up front, so a bad id is a clean 422.

    Without this the FK would still reject the insert, but as an opaque
    IntegrityError after a partial build — worse diagnostics and a wasted round
    trip. One `IN` query names exactly which ids were wrong.
    """
    wanted = set(exercise_ids)
    if not wanted:
        return
    result = await db.execute(select(Exercise.id).where(Exercise.id.in_(wanted)))
    found = {row[0] for row in result}
    missing = wanted - found
    if missing:
        raise UnknownExerciseError(missing)


def _build_entries(items) -> list[WorkoutExercise]:
    """Materialise WorkoutExercise rows, assigning `position` from list order.

    The client never sends `position`: array index *is* the execution order, and
    deriving it here is what makes the `(workout_id, position)` uniqueness
    constraint impossible to violate from the API.
    """
    return [
        WorkoutExercise(
            exercise_id=item.exercise_id,
            position=index,
            sets=item.sets,
            reps=item.reps,
            weight_kg=item.weight_kg,
            rpe=item.rpe,
            notes=item.notes,
        )
        for index, item in enumerate(items)
    ]


async def create_workout(
    db: AsyncSession, *, user_id: uuid.UUID, data: WorkoutCreate
) -> Workout:
    await _ensure_exercises_exist(db, [e.exercise_id for e in data.exercises])

    workout = Workout(
        user_id=user_id,
        performed_on=data.performed_on,
        title=data.title,
        notes=data.notes,
        duration_min=data.duration_min,
        exercises=_build_entries(data.exercises),
    )
    db.add(workout)
    await db.commit()

    # Re-fetch through the full-load path: after commit the nested `exercise`
    # objects are not loaded, and touching them lazily would raise in async.
    reloaded = await get_workout(db, user_id=user_id, workout_id=workout.id)
    assert reloaded is not None  # we just created it, scoped to this same user
    return reloaded


async def get_workout(
    db: AsyncSession, *, user_id: uuid.UUID, workout_id: uuid.UUID
) -> Workout | None:
    stmt = (
        select(Workout)
        .where(Workout.id == workout_id, Workout.user_id == user_id)
        .options(_FULL_LOAD)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_workouts(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[Workout, int]]:
    """List a user's workouts (newest first) with an exercise count per row.

    The count comes from an aggregate join, not from loading each workout's
    children — the list view shows a number, not the sets. Ordering is
    `performed_on` desc then `created_at` desc, so two sessions logged for the
    same day still have a stable, sensible order.
    """
    stmt = (
        select(Workout, func.count(WorkoutExercise.id).label("exercise_count"))
        .outerjoin(WorkoutExercise, WorkoutExercise.workout_id == Workout.id)
        .where(Workout.user_id == user_id)
    )
    if date_from is not None:
        stmt = stmt.where(Workout.performed_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(Workout.performed_on <= date_to)
    stmt = (
        stmt.group_by(Workout.id)
        .order_by(Workout.performed_on.desc(), Workout.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def update_workout(
    db: AsyncSession, *, workout: Workout, data: WorkoutUpdate
) -> Workout:
    """Patch a workout's own fields. Leaves the exercise list untouched."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(workout, field, value)
    await db.commit()
    reloaded = await get_workout(db, user_id=workout.user_id, workout_id=workout.id)
    assert reloaded is not None
    return reloaded


async def replace_workout_exercises(
    db: AsyncSession, *, workout: Workout, data: WorkoutExercisesReplace
) -> Workout:
    """Swap a workout's entire exercise list for a new one, atomically.

    The old rows are deleted and flushed *before* the new ones are inserted:
    otherwise a new entry taking `position=0` would collide with the outgoing
    `position=0` under the uniqueness constraint mid-transaction.
    """
    await _ensure_exercises_exist(db, [e.exercise_id for e in data.exercises])

    workout.exercises.clear()  # delete-orphan marks the old rows for deletion
    await db.flush()  # issue the DELETEs now, freeing their position slots
    workout.exercises.extend(_build_entries(data.exercises))
    await db.commit()

    reloaded = await get_workout(db, user_id=workout.user_id, workout_id=workout.id)
    assert reloaded is not None
    return reloaded


async def delete_workout(db: AsyncSession, *, workout: Workout) -> None:
    """Delete a workout. Its exercise entries go with it (DB CASCADE)."""
    await db.delete(workout)
    await db.commit()
