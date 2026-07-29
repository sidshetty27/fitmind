"""`/api/analytics` — derived training data. Read-only, user-scoped.

Nothing here is stored: every response is computed from the caller's workouts at
request time by `app.crud.analysis`. The ownership rule is the same as everywhere
else — `get_current_user` supplies the id and the aggregation queries filter by
it, so there is no route that can read another user's training.

Separate from `/api/progress`, which records body metrics the user types in.
This router derives numbers from what they logged; that one stores what they
reported. Different sources, different shapes, different routers.

`today` is resolved here rather than deep in the aggregation so the whole request
shares one date, and so tests can pin the window without patching a clock.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import analysis as analysis_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.analysis import (
    ExerciseHistory,
    PersonalRecord,
    TrainingSummary,
    WeekVolume,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# A year of weeks is the practical ceiling for a chart axis, and it bounds the
# work one request can ask the database to do.
_MAX_WEEKS = 52


@router.get("/summary", response_model=TrainingSummary)
async def get_summary(
    weeks: int = Query(
        default=analysis_crud.DEFAULT_WINDOW_WEEKS,
        ge=1,
        le=_MAX_WEEKS,
        description="Length of the trailing window, in whole weeks including this one",
    ),
    exercise_limit: int = Query(
        default=analysis_crud.DEFAULT_EXERCISE_LIMIT,
        ge=1,
        le=50,
        description="Cap on movements returned, most-trained first",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Everything the Progress page needs in one round trip.

    Deliberately one call rather than three: the charts share a window, and
    fetching the pieces separately would let them disagree at a week boundary.
    """
    return await analysis_crud.training_summary(
        db,
        user_id=current_user.id,
        today=date.today(),
        weeks=weeks,
        limit_exercises=exercise_limit,
    )


@router.get("/volume", response_model=list[WeekVolume])
async def get_weekly_volume(
    weeks: int = Query(default=analysis_crud.DEFAULT_WINDOW_WEEKS, ge=1, le=_MAX_WEEKS),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """Weekly load, oldest first. Weeks with no training are absent, not zeroed —
    the caller fills the axis, because only it knows whether a gap means "rested"
    or "outside the window"."""
    return await analysis_crud.weekly_volume(
        db,
        user_id=current_user.id,
        since=analysis_crud.window_start(date.today(), weeks),
    )


@router.get("/records", response_model=list[PersonalRecord])
async def get_personal_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """All-time bests per movement, most recently trained first."""
    return await analysis_crud.personal_records(db, user_id=current_user.id)


@router.get("/exercises/{exercise_id}", response_model=ExerciseHistory)
async def get_exercise_history(
    exercise_id: uuid.UUID,
    weeks: int | None = Query(
        default=None,
        ge=1,
        le=_MAX_WEEKS,
        description="Trailing window; omit for the movement's full history",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One movement's series — the "how is my bench going" query.

    404 when the caller has never logged this movement. That covers an unknown id
    and another user's data identically, so the response never reveals which.
    """
    histories = await analysis_crud.exercise_history(
        db,
        user_id=current_user.id,
        since=analysis_crud.window_start(date.today(), weeks) if weeks else None,
        exercise_id=exercise_id,
        limit_exercises=None,
    )
    if not histories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No logged sessions for that exercise",
        )
    return histories[0]
