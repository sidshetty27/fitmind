"""Data access for `users` — in particular, the Clerk → internal user link.

**How the two identity systems are joined.** Clerk authenticates the request and
gives us a subject claim (`sub`) which is the Clerk user id. Everything in our
schema is keyed by `users.id`. `users.clerk_id` is the one place those two worlds
touch, and `get_or_create_user_by_clerk_id` below is the one function that
crosses the boundary. Keeping it to a single function means the rest of the
codebase only ever deals in internal ids.

**Just-in-time provisioning, not a webhook (yet).** There are two ways to get a
Clerk user into this table:

  1. *JIT* — on the first authenticated request, look up `clerk_id`; if absent,
     insert. Implemented here.
  2. *Webhook* — Clerk POSTs `user.created` to us and we insert immediately.

JIT is what makes the system correct: it cannot be missed, has no delivery
guarantees to depend on, and self-heals if a webhook was ever dropped or if the
database was restored from a backup taken before a signup. A `user.created`
webhook is still worth adding in Phase 4, but as an *optimisation* (row exists
before first request) and for *updates* (email changes, deletions) — never as the
only path, because then a single missed delivery leaves an authenticated user
with no row and every one of their requests failing.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_clerk_id(db: AsyncSession, clerk_id: str) -> User | None:
    """Look up the internal user for a Clerk subject. The hot path for auth."""
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_or_create_user_by_clerk_id(
    db: AsyncSession,
    *,
    clerk_id: str,
    email: str,
    name: str | None = None,
) -> User:
    """Return the user for this Clerk id, creating the row on first sight.

    Written as an INSERT ... ON CONFLICT DO NOTHING rather than the intuitive
    "SELECT, and INSERT if missing". The intuitive version has a real race: a
    freshly signed-up user's browser fires several requests at once, two of them
    find no row, and both INSERT — one crashes on the unique constraint. Letting
    Postgres arbitrate via the constraint we already declared makes the operation
    atomic, so concurrent callers converge on one row.

    `DO NOTHING` (not `DO UPDATE`) is the right conflict action: Clerk stays
    authoritative for email and name, but overwriting local columns on every
    request would fight with any profile edits the user makes in FitMind. Syncing
    those fields is the webhook's job.
    """
    stmt = (
        pg_insert(User)
        .values(clerk_id=clerk_id, email=email, name=name)
        .on_conflict_do_nothing(index_elements=["clerk_id"])
        .returning(User)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # DO NOTHING returns no row when the insert was skipped, which means the
        # row already existed (created earlier, or by a concurrent request).
        user = await get_user_by_clerk_id(db, clerk_id)

    await db.commit()

    if user is None:  # pragma: no cover - both the insert and the read failed
        raise RuntimeError(f"Could not create or load user for clerk_id={clerk_id!r}")

    return user
