"""What a plan entitles you to, and the dependency that enforces it.

Every "can this user do that?" decision lives here rather than in the routes. The
routes are then free of pricing policy, and changing what premium includes is one
file rather than a search for scattered `if` statements.

The split mirrors the coach's:

  - `is_premium` and `quota_state` are **pure functions** over rows already
    fetched. No I/O, no framework — unit-testable with plain objects.
  - `require_ai_quota` is the FastAPI dependency that does the fetching and turns
    a refusal into an HTTP response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.crud import ai_analysis as analysis_crud
from app.crud import subscription as subscription_crud
from app.db.session import get_db
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)

# Stripe statuses that grant premium.
#
# `active` and `trialing` are the uncontroversial two. `past_due` is the judgement
# call: it means a renewal payment failed and Stripe is retrying, which it will go
# on doing for days before giving up and moving the subscription to `canceled` or
# `unpaid`. Revoking access at the first failed charge would lock a paying
# customer out of their own training history because their card expired — while
# Stripe is still, quite likely, about to collect. We keep them in, and let
# Stripe's dunning decide the outcome. The cost of being wrong is a few days of
# access; the cost of the other choice is the angriest support email you will get.
#
# Everything else — `incomplete`, `incomplete_expired`, `canceled`, `unpaid`,
# `paused` — is not premium.
PREMIUM_STATUSES = frozenset({"active", "trialing", "past_due"})

# The window the free allowance is measured over. Rolling rather than calendar —
# see `crud.ai_analysis.count_today` for why.
QUOTA_WINDOW = timedelta(days=1)

# Machine-readable marker on the 402 body. The frontend keys its upgrade prompt
# off this rather than off the message text, so the copy can be reworded without
# breaking the UI.
QUOTA_ERROR_CODE = "free_tier_limit_reached"


def is_premium(subscription: Subscription | None) -> bool:
    """Whether this billing row entitles its owner to premium features.

    `None` means the user never opened checkout, which is the ordinary state of a
    free account — not an error and not a missing record.

    An unrecognised status is treated as **not** premium, and logged. Stripe can
    add statuses, and this is the honest response to one: refusing to guess, and
    saying so somewhere a human will see it. The alternative — treating unknown
    as entitled — would hand out the product on the strength of a value nobody
    has read yet. The log line is the part that matters; it is what turns "a
    customer says they paid" into a one-line fix.
    """
    if subscription is None or subscription.status is None:
        return False

    if subscription.status in PREMIUM_STATUSES:
        return True

    if subscription.status not in _KNOWN_NON_PREMIUM_STATUSES:
        logger.warning(
            "Unrecognised Stripe subscription status %r on subscription %s — "
            "treating as not premium. If this status should grant access, add it "
            "to PREMIUM_STATUSES in app/core/entitlements.py.",
            subscription.status,
            subscription.id,
        )

    return False


# Statuses we know about and have decided are not premium. Kept separate from
# PREMIUM_STATUSES purely so `is_premium` can tell "decided no" from "never heard
# of it" and only log the second.
_KNOWN_NON_PREMIUM_STATUSES = frozenset(
    {"incomplete", "incomplete_expired", "canceled", "unpaid", "paused"}
)


@dataclass(frozen=True)
class QuotaState:
    """A user's standing against the free AI allowance.

    Returned whole, rather than as a bare bool, because the same three numbers
    answer both questions the app has: may this run proceed, and what should the
    Coach page tell someone about where they stand.
    """

    premium: bool
    limit: int
    used: int
    resets_at: datetime | None

    @property
    def unlimited(self) -> bool:
        return self.premium

    @property
    def remaining(self) -> int:
        """Runs left in the window. `-1` stands for unlimited."""
        if self.premium:
            return -1
        return max(0, self.limit - self.used)

    @property
    def exceeded(self) -> bool:
        return not self.premium and self.used >= self.limit


async def quota_state(db: AsyncSession, *, user: User) -> QuotaState:
    """Where this user stands against the free allowance, right now.

    Premium short-circuits before the count: an unlimited plan makes the number
    irrelevant, and there is no reason to pay for the query.
    """
    subscription = await subscription_crud.get_by_user_id(db, user_id=user.id)
    premium = is_premium(subscription)

    if premium:
        return QuotaState(
            premium=True,
            limit=settings.free_daily_ai_analyses,
            used=0,
            resets_at=None,
        )

    since = datetime.now(timezone.utc) - QUOTA_WINDOW
    used = await analysis_crud.count_since(db, user_id=user.id, since=since)

    resets_at = None
    if used >= settings.free_daily_ai_analyses:
        oldest = await analysis_crud.oldest_created_at_since(
            db, user_id=user.id, since=since
        )
        if oldest is not None:
            # The oldest run in the window is the one whose expiry frees a slot.
            resets_at = oldest + QUOTA_WINDOW

    return QuotaState(
        premium=False,
        limit=settings.free_daily_ai_analyses,
        used=used,
        resets_at=resets_at,
    )


async def require_ai_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: allow an AI coach run, or refuse with a 402.

    Drops into a route in place of `get_current_user` — it returns the same
    `User`, so the handler body does not change.

    **402 Payment Required, not 429.** Both describe a refused request, but they
    ask for different things: 429 says wait, 402 says pay. A user who has used
    their three free runs is not going too fast, and telling them to slow down
    would be a lie that hides the actual remedy. The frontend needs to render an
    upgrade prompt for one and a "try again shortly" for the other, so the status
    codes have to be distinguishable.

    The body is a dict rather than a string so the frontend can key off `code`
    instead of parsing prose. `lib/api.ts` already preserves non-string details
    on `ApiError.detail`.
    """
    state = await quota_state(db, user=current_user)

    if state.exceeded:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": QUOTA_ERROR_CODE,
                "message": (
                    f"You have used all {state.limit} free coach analyses for "
                    "today. Upgrade for unlimited coaching, or come back when "
                    "your allowance resets."
                ),
                "limit": state.limit,
                "used": state.used,
                "resets_at": state.resets_at.isoformat() if state.resets_at else None,
            },
        )

    return current_user


__all__ = [
    "PREMIUM_STATUSES",
    "QUOTA_ERROR_CODE",
    "QuotaState",
    "is_premium",
    "quota_state",
    "require_ai_quota",
]
