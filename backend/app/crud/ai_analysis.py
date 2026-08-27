"""Stored AI coach runs — always scoped to the owning user.

Same ownership rule as every other module here: the `user_id` predicate is on the
query, so no path can read another user's coaching history.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis import AiAnalysis


async def create_analysis(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    window_start: date,
    window_end: date,
    workout_count: int,
    findings: list[dict[str, Any]],
    narrative: str | None,
    model: str | None,
) -> AiAnalysis:
    """Record one run. Commits, because an analysis is a complete unit of work."""
    analysis = AiAnalysis(
        user_id=user_id,
        window_start=window_start,
        window_end=window_end,
        workout_count=workout_count,
        findings=findings,
        narrative=narrative,
        model=model,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


async def list_analyses(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> list[AiAnalysis]:
    """The user's coaching history, newest first."""
    stmt = (
        select(AiAnalysis)
        .where(AiAnalysis.user_id == user_id)
        .order_by(AiAnalysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_analysis(
    db: AsyncSession, *, user_id: uuid.UUID, analysis_id: uuid.UUID
) -> AiAnalysis | None:
    """One analysis the caller owns, or `None`."""
    stmt = select(AiAnalysis).where(
        AiAnalysis.id == analysis_id, AiAnalysis.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_since(
    db: AsyncSession, *, user_id: uuid.UUID, since: datetime
) -> int:
    """How many analyses this user has run since `since`.

    This is the whole implementation of Phase 8's "unlimited AI analyses" gate —
    a quota is a row count, which is why runs are stored rather than computed and
    discarded.
    """
    stmt = select(func.count(AiAnalysis.id)).where(
        AiAnalysis.user_id == user_id, AiAnalysis.created_at >= since
    )
    return (await db.execute(stmt)).scalar_one()


async def count_all_since(db: AsyncSession, *, since: datetime) -> int:
    """How many analyses **every** user has run since `since`.

    The one query in this module with no `user_id` predicate, which is worth
    saying out loud in a file whose opening line is that everything is scoped to
    its owner. It is deliberate and it is not a read of anyone's data: the result
    is a single integer over all rows, used only to decide whether the deployment
    as a whole has spent its daily allowance of model calls.

    That ceiling cannot be expressed per user. Accounts are free and unlimited,
    so a per-account limit bounds what one account costs and says nothing about
    what the deployment costs — see `app/core/entitlements.py`.
    """
    stmt = select(func.count(AiAnalysis.id)).where(AiAnalysis.created_at >= since)
    return (await db.execute(stmt)).scalar_one()


async def oldest_created_at_all_since(
    db: AsyncSession, *, since: datetime
) -> datetime | None:
    """When the earliest analysis by anyone still inside the window was run.

    The global counterpart of `oldest_created_at_since`, and used for the same
    thing: that run is the one whose expiry frees a slot, so `oldest + window` is
    the earliest moment the ceiling could lift. It is what makes a `Retry-After`
    a real answer rather than a guess.
    """
    stmt = select(func.min(AiAnalysis.created_at)).where(AiAnalysis.created_at >= since)
    return (await db.execute(stmt)).scalar_one_or_none()


async def oldest_created_at_since(
    db: AsyncSession, *, user_id: uuid.UUID, since: datetime
) -> datetime | None:
    """When the earliest analysis still inside the window was run.

    Only interesting once someone is over quota: that run is the one whose
    expiry frees up a slot, so `oldest + 24h` is when they can next analyse.
    Without it a "limit reached" message can only say "later", which is the kind
    of answer that gets reported as a bug.

    `None` when there are no analyses in the window.
    """
    stmt = select(func.min(AiAnalysis.created_at)).where(
        AiAnalysis.user_id == user_id, AiAnalysis.created_at >= since
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_today(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Analyses in the last 24 hours — a rolling window, not a calendar day.

    A calendar-day reset would let a user run their whole allowance at 23:59 and
    again at 00:01. Rolling avoids that without needing a timezone for the user.
    """
    return await count_since(
        db, user_id=user_id, since=datetime.now(timezone.utc) - timedelta(days=1)
    )


__all__ = [
    "count_all_since",
    "count_since",
    "count_today",
    "create_analysis",
    "get_analysis",
    "list_analyses",
    "oldest_created_at_all_since",
    "oldest_created_at_since",
]
