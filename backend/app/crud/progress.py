"""Progress-entry data access — daily body/lifestyle metrics, scoped to the user.

The write path is an UPSERT keyed on `(user_id, recorded_on)`. That is what makes
"log today's weight" idempotent: a double-tap updates the day's row instead of
racing to insert a duplicate the unique constraint would then reject.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ProgressEntry
from app.schemas.progress import ProgressUpsert


async def upsert_progress(
    db: AsyncSession, *, user_id: uuid.UUID, data: ProgressUpsert
) -> ProgressEntry:
    """Create or merge a day's entry, updating only the fields that were sent.

    Merge, not overwrite: logging sleep for a day that already has a bodyweight
    must not null the bodyweight. So only the explicitly-provided fields go into
    the `DO UPDATE` set; omitted ones keep their stored value. `updated_at` is
    bumped explicitly because a core `INSERT ... ON CONFLICT` does not trigger the
    ORM-side `onupdate`.
    """
    provided = data.model_dump(exclude_unset=True, exclude={"recorded_on"})

    values = {"user_id": user_id, "recorded_on": data.recorded_on, **provided}
    stmt = pg_insert(ProgressEntry).values(**values)

    if provided:
        update_set = {key: getattr(stmt.excluded, key) for key in provided}
        update_set["updated_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "recorded_on"], set_=update_set
        )
    else:
        # Nothing but the date was sent — ensure the row exists, change nothing.
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["user_id", "recorded_on"]
        )

    stmt = stmt.returning(ProgressEntry)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    await db.commit()

    if entry is None:
        # DO NOTHING skipped the write because the row already existed.
        entry = await get_progress_by_date(db, user_id=user_id, on=data.recorded_on)
    assert entry is not None
    return entry


async def get_progress_by_date(
    db: AsyncSession, *, user_id: uuid.UUID, on: date
) -> ProgressEntry | None:
    stmt = select(ProgressEntry).where(
        ProgressEntry.user_id == user_id, ProgressEntry.recorded_on == on
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 90,
    offset: int = 0,
) -> list[ProgressEntry]:
    """List a user's entries, newest day first — the shape a trend chart wants."""
    stmt = select(ProgressEntry).where(ProgressEntry.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(ProgressEntry.recorded_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProgressEntry.recorded_on <= date_to)
    stmt = stmt.order_by(ProgressEntry.recorded_on.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_progress(db: AsyncSession, *, entry: ProgressEntry) -> None:
    await db.delete(entry)
    await db.commit()
