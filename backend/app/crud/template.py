"""Workout template data access — always scoped to the owning user.

Same contract as `crud/workout.py`: every read and write carries a `user_id`
predicate, so there is no code path that returns or mutates another user's
template. A missing or foreign id comes back as `None`, which the router turns
into a 404.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.workout import (
    UnknownExerciseError,
    _ensure_exercises_exist,
    create_workout,
)
from app.models.workout import Workout
from app.models.workout_template import WorkoutTemplate
from app.models.workout_template_exercise import WorkoutTemplateExercise
from app.schemas.template import (
    TemplateApply,
    TemplateCreate,
    TemplateExercisesReplace,
    TemplateUpdate,
)
from app.schemas.workout import WorkoutCreate, WorkoutExerciseCreate

# `_ensure_exercises_exist` is imported from the workout module rather than
# reimplemented: templates reference the same shared catalog and must raise the
# same `UnknownExerciseError` for the same 422. Two copies of that query would be
# two things to keep in step.


class DuplicateTemplateNameError(Exception):
    """Raised when a user already has a template with the requested name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"You already have a template named {name!r}.")


# Same load rule as workouts: the template's exercises, each with its catalog
# entry, via selectinload rather than a row-multiplying JOIN.
_FULL_LOAD = selectinload(WorkoutTemplate.exercises).selectinload(
    WorkoutTemplateExercise.exercise
)


def _build_entries(items) -> list[WorkoutTemplateExercise]:
    """Materialise rows, assigning `position` from list order."""
    return [
        WorkoutTemplateExercise(
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


async def _name_taken(
    db: AsyncSession, *, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> bool:
    """Check the (user_id, name) uniqueness before the DB has to.

    The constraint is authoritative, but hitting it produces an opaque
    IntegrityError. Asking first turns "you already have a template called Push
    Day A" into a message the UI can put next to the name field.
    """
    stmt = select(WorkoutTemplate.id).where(
        WorkoutTemplate.user_id == user_id, WorkoutTemplate.name == name
    )
    if exclude_id is not None:
        stmt = stmt.where(WorkoutTemplate.id != exclude_id)
    result = await db.execute(stmt)
    return result.first() is not None


async def create_template(
    db: AsyncSession, *, user_id: uuid.UUID, data: TemplateCreate
) -> WorkoutTemplate:
    await _ensure_exercises_exist(db, [e.exercise_id for e in data.exercises])
    if await _name_taken(db, user_id=user_id, name=data.name):
        raise DuplicateTemplateNameError(data.name)

    template = WorkoutTemplate(
        user_id=user_id,
        name=data.name,
        description=data.description,
        exercises=_build_entries(data.exercises),
    )
    db.add(template)
    await db.commit()

    reloaded = await get_template(db, user_id=user_id, template_id=template.id)
    assert reloaded is not None  # just created, scoped to this same user
    return reloaded


async def get_template(
    db: AsyncSession, *, user_id: uuid.UUID, template_id: uuid.UUID
) -> WorkoutTemplate | None:
    stmt = (
        select(WorkoutTemplate)
        .where(WorkoutTemplate.id == template_id, WorkoutTemplate.user_id == user_id)
        .options(_FULL_LOAD)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_templates(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[tuple[WorkoutTemplate, int]]:
    """A user's templates, alphabetical, with an exercise count per row."""
    stmt = (
        select(WorkoutTemplate, func.count(WorkoutTemplateExercise.id))
        .outerjoin(
            WorkoutTemplateExercise,
            WorkoutTemplateExercise.template_id == WorkoutTemplate.id,
        )
        .where(WorkoutTemplate.user_id == user_id)
        .group_by(WorkoutTemplate.id)
        .order_by(WorkoutTemplate.name.asc())
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def update_template(
    db: AsyncSession, *, template: WorkoutTemplate, data: TemplateUpdate
) -> WorkoutTemplate:
    fields = data.model_dump(exclude_unset=True)

    new_name = fields.get("name")
    if new_name is not None and new_name != template.name:
        if await _name_taken(
            db, user_id=template.user_id, name=new_name, exclude_id=template.id
        ):
            raise DuplicateTemplateNameError(new_name)

    for field, value in fields.items():
        setattr(template, field, value)
    await db.commit()

    reloaded = await get_template(
        db, user_id=template.user_id, template_id=template.id
    )
    assert reloaded is not None
    return reloaded


async def replace_template_exercises(
    db: AsyncSession, *, template: WorkoutTemplate, data: TemplateExercisesReplace
) -> WorkoutTemplate:
    """Swap the whole exercise list atomically.

    Old rows are deleted and flushed *before* the new ones are inserted, so an
    incoming `position=0` cannot collide with the outgoing one mid-transaction.
    Same ordering requirement as `replace_workout_exercises`.
    """
    await _ensure_exercises_exist(db, [e.exercise_id for e in data.exercises])

    template.exercises.clear()
    await db.flush()
    template.exercises.extend(_build_entries(data.exercises))
    await db.commit()

    reloaded = await get_template(db, user_id=template.user_id, template_id=template.id)
    assert reloaded is not None
    return reloaded


async def delete_template(db: AsyncSession, *, template: WorkoutTemplate) -> None:
    """Delete a template. Its exercise rows go with it (DB CASCADE).

    Workouts already logged from this template are untouched — they were copies,
    never references.
    """
    await db.delete(template)
    await db.commit()


async def apply_template(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    template: WorkoutTemplate,
    data: TemplateApply,
) -> Workout:
    """Create a real workout from a template's plan.

    A copy, not a link. The new workout owns its own exercise rows from this
    moment on, so editing the template later cannot rewrite a session that has
    already been logged — and adjusting the weights you actually hit does not
    corrupt the plan.

    Delegates to `create_workout` rather than building the rows here: that keeps
    catalog validation, position assignment, and the post-commit reload in one
    place instead of two that can drift.
    """
    payload = WorkoutCreate(
        performed_on=data.performed_on,
        # Falling back to the template's name is what makes "log my Push Day A"
        # a single click with a sensibly-titled result.
        title=data.title if data.title is not None else template.name,
        notes=data.notes,
        duration_min=data.duration_min,
        exercises=[
            WorkoutExerciseCreate(
                exercise_id=entry.exercise_id,
                sets=entry.sets,
                reps=entry.reps,
                weight_kg=entry.weight_kg,
                rpe=entry.rpe,
                notes=entry.notes,
            )
            # `template.exercises` is ordered by position via the relationship, so
            # the copy preserves the planned order.
            for entry in template.exercises
        ],
    )
    return await create_workout(db, user_id=user_id, data=payload)


__all__ = [
    "DuplicateTemplateNameError",
    "UnknownExerciseError",
    "apply_template",
    "create_template",
    "delete_template",
    "get_template",
    "list_templates",
    "replace_template_exercises",
    "update_template",
]
