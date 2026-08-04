"""Data access for `subscriptions`.

Two callers, with very different rules:

  - **Request paths** may only *read* (`get_by_user_id`) or link a Stripe customer
    to an account (`link_customer`). They must never touch `status`.
  - **The Stripe webhook** is the only writer of Stripe-owned state, through
    `apply_stripe_state`. That is the whole reason entitlement can be trusted: if
    a request path could set `status`, the column would stop meaning "Stripe
    agrees this person paid" and start meaning "some code once said so".

Lookups are by `stripe_customer_id` rather than `user_id` on the webhook side,
because a Stripe event knows about customers and subscriptions — it has never
heard of a FitMind user id.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.subscription import Subscription


async def get_by_user_id(db: AsyncSession, *, user_id: uuid.UUID) -> Subscription | None:
    """The user's billing row, or `None` for anyone who never opened checkout.

    `None` is a normal, expected answer meaning "free tier" — not a missing
    record. Callers must not treat it as an error.

    Queried explicitly rather than read off `User.subscription`. Under async
    SQLAlchemy a lazy relationship access outside a loading context raises
    `MissingGreenlet`, and the failure surfaces far from the attribute that
    caused it. One explicit select is both safer and easier to read.
    """
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_by_customer_id(
    db: AsyncSession, *, stripe_customer_id: str
) -> Subscription | None:
    """The billing row for a Stripe customer. The webhook's way in."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_customer_id == stripe_customer_id
        )
    )
    return result.scalar_one_or_none()


async def link_customer(
    db: AsyncSession, *, user_id: uuid.UUID, stripe_customer_id: str
) -> Subscription:
    """Record that this account owns this Stripe customer. Idempotent.

    Written as INSERT ... ON CONFLICT DO NOTHING for the same reason
    `get_or_create_user_by_clerk_id` is: two clicks on Upgrade fire two requests,
    both find no row, and both insert — one dies on `uq_subscriptions_user_id`.
    Letting Postgres arbitrate makes concurrent callers converge on one row.

    `DO NOTHING` rather than `DO UPDATE` matters here beyond the usual argument.
    If a row already exists it already names a Stripe customer, and overwriting
    that would strand the old customer — along with its payment methods, its
    invoice history, and possibly a live subscription still charging the card.
    So the existing customer always wins, and the caller gets it back to reuse.
    """
    stmt = (
        pg_insert(Subscription)
        .values(user_id=user_id, stripe_customer_id=stripe_customer_id)
        .on_conflict_do_nothing(index_elements=["user_id"])
        .returning(Subscription)
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if subscription is None:
        # The insert was skipped, so a row already existed.
        subscription = await get_by_user_id(db, user_id=user_id)

    await db.commit()

    if subscription is None:  # pragma: no cover - insert skipped and read empty
        raise RuntimeError(f"Could not link Stripe customer for user_id={user_id}")

    return subscription


async def apply_stripe_state(
    db: AsyncSession,
    *,
    stripe_customer_id: str,
    stripe_subscription_id: str | None,
    status: str | None,
    price_id: str | None,
    current_period_end: datetime | None,
    cancel_at_period_end: bool,
) -> Subscription | None:
    """Overwrite this customer's billing state with Stripe's version of it.

    A whole-state write, not a delta, and that is the point. Stripe retries
    deliveries and does not promise ordering, so applying events as increments
    would let a redelivered `created` land after an `updated` and quietly
    downgrade a paying customer. Writing the full canonical state makes both
    duplicate and out-of-order delivery harmless: the last write says the same
    thing as the one before it, because the caller re-fetched it from Stripe.

    Returns `None` when no row matches the customer. That is not an error — the
    Stripe account may serve something other than this app, and a webhook for a
    customer we never created is simply not ours. Inventing a row is impossible
    anyway: there is no user to attach it to.
    """
    subscription = await get_by_customer_id(db, stripe_customer_id=stripe_customer_id)
    if subscription is None:
        return None

    subscription.stripe_subscription_id = stripe_subscription_id
    subscription.status = status
    subscription.price_id = price_id
    subscription.current_period_end = current_period_end
    subscription.cancel_at_period_end = cancel_at_period_end
    # `onupdate` on the mixin covers this, but only when SQLAlchemy sees a real
    # change. A redelivered identical event would otherwise leave `updated_at`
    # showing the first delivery, which is exactly when you are trying to work
    # out whether the webhook is still alive.
    subscription.updated_at = func.now()

    await db.commit()
    await db.refresh(subscription)
    return subscription


__all__ = [
    "apply_stripe_state",
    "get_by_customer_id",
    "get_by_user_id",
    "link_customer",
]
