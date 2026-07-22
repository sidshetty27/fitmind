"""`/api/exercises` — read-only access to the shared movement catalog.

Auth-gated even though the catalog is not sensitive: every caller of this API is a
signed-in user picking exercises to log, so requiring the token keeps the API
surface uniform and gives us per-user rate limiting later for free.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import exercise as exercise_crud
from app.db.session import get_db
from app.models.enums import Equipment, MuscleGroup
from app.models.user import User
from app.schemas.exercise import ExerciseRead

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseRead])
async def list_exercises(
    muscle_group: MuscleGroup | None = None,
    equipment: Equipment | None = None,
    search: str | None = Query(default=None, description="Case-insensitive name match"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await exercise_crud.list_exercises(
        db,
        muscle_group=muscle_group,
        equipment=equipment,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{exercise_id}", response_model=ExerciseRead)
async def get_exercise(
    exercise_id: uuid.UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exercise = await exercise_crud.get_exercise(db, exercise_id)
    if exercise is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found"
        )
    return exercise
