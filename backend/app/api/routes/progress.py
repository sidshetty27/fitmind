"""`/api/progress` — daily body/lifestyle metrics, user-scoped.

Addressed by calendar date, not by row id: there is exactly one entry per user per
day, so `recorded_on` is the natural, stable handle. `PUT` upserts that day (log or
re-log today's weight idempotently); `GET` lists a range for charting.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import progress as progress_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.progress import ProgressRead, ProgressUpsert

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.put("", response_model=ProgressRead)
async def upsert_progress(
    data: ProgressUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or merge the entry for `recorded_on`. Idempotent by design."""
    return await progress_crud.upsert_progress(db, user_id=current_user.id, data=data)


@router.get("", response_model=list[ProgressRead])
async def list_progress(
    date_from: date | None = Query(default=None, description="Include entries on/after"),
    date_to: date | None = Query(default=None, description="Include entries on/before"),
    limit: int = Query(default=90, ge=1, le=366),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await progress_crud.list_progress(
        db,
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{recorded_on}", response_model=ProgressRead)
async def get_progress(
    recorded_on: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await progress_crud.get_progress_by_date(
        db, user_id=current_user.id, on=recorded_on
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No entry for that date"
        )
    return entry


@router.delete("/{recorded_on}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_progress(
    recorded_on: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await progress_crud.get_progress_by_date(
        db, user_id=current_user.id, on=recorded_on
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No entry for that date"
        )
    await progress_crud.delete_progress(db, entry=entry)
