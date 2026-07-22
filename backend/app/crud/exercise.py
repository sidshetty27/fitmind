"""Read access to the shared exercise catalog.

The catalog is seed data (migration `0002`), so there is no create/update/delete
here — the API only ever reads it. Everything is a plain filtered list because
that is exactly what a "pick an exercise" UI needs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Equipment, MuscleGroup
from app.models.exercise import Exercise


async def list_exercises(
    db: AsyncSession,
    *,
    muscle_group: MuscleGroup | None = None,
    equipment: Equipment | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Exercise]:
    """List catalog movements, optionally filtered by muscle, equipment, or name."""
    stmt = select(Exercise)
    if muscle_group is not None:
        stmt = stmt.where(Exercise.primary_muscle_group == muscle_group)
    if equipment is not None:
        stmt = stmt.where(Exercise.equipment == equipment)
    if search:
        # Case-insensitive substring match. `ilike` is fine for a ~32-row catalog;
        # if the catalog ever grows large enough to matter, a trigram index is the
        # upgrade, not a rewrite.
        stmt = stmt.where(Exercise.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Exercise.name).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_exercise(db: AsyncSession, exercise_id: uuid.UUID) -> Exercise | None:
    return await db.get(Exercise, exercise_id)
