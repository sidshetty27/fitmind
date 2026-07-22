"""`/api/workouts` — the core logging surface. Every route is user-scoped.

Access control is structural: `get_current_user` supplies the id, and every CRUD
call filters by it. A workout that is not the caller's returns 404 (not 403), so
the API never even confirms that another user's workout exists.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import workout as workout_crud
from app.crud.workout import UnknownExerciseError
from app.db.session import get_db
from app.models.user import User
from app.models.workout import Workout
from app.schemas.workout import (
    WorkoutCreate,
    WorkoutExercisesReplace,
    WorkoutListItem,
    WorkoutRead,
    WorkoutUpdate,
)

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

_UNKNOWN_EXERCISE = status.HTTP_422_UNPROCESSABLE_ENTITY


async def _get_owned_or_404(
    db: AsyncSession, user: User, workout_id: uuid.UUID
) -> Workout:
    """Load a workout the caller owns, or raise 404. The one ownership gate."""
    workout = await workout_crud.get_workout(db, user_id=user.id, workout_id=workout_id)
    if workout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    return workout


@router.post("", response_model=WorkoutRead, status_code=status.HTTP_201_CREATED)
async def create_workout(
    data: WorkoutCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await workout_crud.create_workout(db, user_id=current_user.id, data=data)
    except UnknownExerciseError as exc:
        raise HTTPException(status_code=_UNKNOWN_EXERCISE, detail=str(exc)) from exc


@router.get("", response_model=list[WorkoutListItem])
async def list_workouts(
    date_from: date | None = Query(default=None, description="Include workouts on/after"),
    date_to: date | None = Query(default=None, description="Include workouts on/before"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkoutListItem]:
    rows = await workout_crud.list_workouts(
        db,
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    # The exercise_count is an aggregate column, not a model attribute, so build
    # the list items explicitly rather than from_attributes.
    return [
        WorkoutListItem(
            id=w.id,
            performed_on=w.performed_on,
            title=w.title,
            duration_min=w.duration_min,
            exercise_count=count,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w, count in rows
    ]


@router.get("/{workout_id}", response_model=WorkoutRead)
async def get_workout(
    workout_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_or_404(db, current_user, workout_id)


@router.patch("/{workout_id}", response_model=WorkoutRead)
async def update_workout(
    workout_id: uuid.UUID,
    data: WorkoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workout = await _get_owned_or_404(db, current_user, workout_id)
    return await workout_crud.update_workout(db, workout=workout, data=data)


@router.put("/{workout_id}/exercises", response_model=WorkoutRead)
async def replace_workout_exercises(
    workout_id: uuid.UUID,
    data: WorkoutExercisesReplace,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace a workout's entire exercise list in one atomic operation."""
    workout = await _get_owned_or_404(db, current_user, workout_id)
    try:
        return await workout_crud.replace_workout_exercises(db, workout=workout, data=data)
    except UnknownExerciseError as exc:
        raise HTTPException(status_code=_UNKNOWN_EXERCISE, detail=str(exc)) from exc


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    workout = await _get_owned_or_404(db, current_user, workout_id)
    await workout_crud.delete_workout(db, workout=workout)
