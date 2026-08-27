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
import math
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

# The two rate-limit windows. Separate constants from QUOTA_WINDOW because they
# are a different kind of rule — see the `RateLimit` docstring.
USER_RATE_WINDOW = timedelta(hours=1)
GLOBAL_RATE_WINDOW = timedelta(days=1)

# Distinct codes, because they call for opposite responses. `rate_limited` is
# about this caller and clears on its own within the hour. `ai_capacity_reached`
# is about the deployment: every user is refused, and if it fires on real
# traffic the fix is to raise `AI_RATE_LIMIT_GLOBAL_DAILY`, not to wait. Folding
# them into one code would make the operational signal unreadable.
RATE_LIMIT_ERROR_CODE = "rate_limited"
CAPACITY_ERROR_CODE = "ai_capacity_reached"


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


@dataclass(frozen=True)
class RateLimit:
    """One counted window, and whether it is full.

    A rate limit and the free-tier quota look alike — both count runs and both
    refuse — and they are not the same rule. The quota is *pricing*: it decides
    what a plan includes, it exempts premium, and the remedy is to pay. A rate
    limit is *cost control*: nothing is exempt, and the remedy is to wait. They
    are modelled separately, and answered with different status codes, so
    neither can quietly acquire the other's semantics.

    Purely a value: the counting happens in `ai_rate_limits`, which keeps this
    testable with plain numbers.
    """

    code: str
    limit: int
    used: int
    window: timedelta
    # Oldest run still inside the window. Its expiry is what frees a slot, so it
    # is the only honest basis for a Retry-After.
    oldest: datetime | None
    message: str

    @property
    def exceeded(self) -> bool:
        return self.used >= self.limit

    def retry_after_seconds(self, *, now: datetime) -> int:
        """Whole seconds until a slot frees, never less than one.

        With no oldest run there is nothing to expire — which can only happen at
        a limit of 0, where the window never frees anything and the answer is
        the window itself.

        Rounded up: a client that retries at the floor of a fractional second
        arrives before the row has aged out and is refused a second time, which
        reads as the limit being broken.
        """
        if self.oldest is None:
            return max(1, int(self.window.total_seconds()))
        remaining = (self.oldest + self.window) - now
        return max(1, math.ceil(remaining.total_seconds()))


async def ai_rate_limits(db: AsyncSession, *, user: User) -> list[RateLimit]:
    """The rate limits on an AI run, in the order they should be applied.

    Global first. It describes the deployment rather than the caller, so when it
    is full the answer is the same for everyone and there is no point costing a
    second query to find out how fast this particular user was going.

    **A known imprecision, stated rather than hidden.** These counts read rows
    that previous runs *finished* writing, and the row for this run is written
    after the model call returns. Two requests that overlap can therefore both
    pass the same check. The overshoot is bounded by the number of coach
    requests in flight at once — on a single worker with 0.1 CPU, a very small
    number — and the limits are a budget guard rather than an invariant, so this
    is the right trade against reserving a row before the call and having to
    reconcile the ones whose call then failed. If the ceiling ever needs to be
    exact, that reservation is the design, not a lock.
    """
    now = datetime.now(timezone.utc)

    global_since = now - GLOBAL_RATE_WINDOW
    global_used = await analysis_crud.count_all_since(db, since=global_since)
    global_limit = RateLimit(
        code=CAPACITY_ERROR_CODE,
        limit=settings.ai_rate_limit_global_daily,
        used=global_used,
        window=GLOBAL_RATE_WINDOW,
        oldest=(
            await analysis_crud.oldest_created_at_all_since(db, since=global_since)
            if global_used >= settings.ai_rate_limit_global_daily
            else None
        ),
        message=(
            "The coach is at its daily limit across all users and is not "
            "running new analyses right now. Your existing analyses are "
            "unaffected. Please try again later."
        ),
    )
    if global_limit.exceeded:
        # Warning rather than info: on a healthy deployment this never fires, and
        # when it does it is either an attack or a ceiling that has become too
        # low for real traffic. Both are worth finding in a log.
        logger.warning(
            "AI capacity ceiling reached: %s runs in the last %s (limit %s). "
            "Raise AI_RATE_LIMIT_GLOBAL_DAILY if this is legitimate traffic.",
            global_used,
            GLOBAL_RATE_WINDOW,
            settings.ai_rate_limit_global_daily,
        )
        return [global_limit]

    user_since = now - USER_RATE_WINDOW
    user_used = await analysis_crud.count_since(
        db, user_id=user.id, since=user_since
    )
    user_limit = RateLimit(
        code=RATE_LIMIT_ERROR_CODE,
        limit=settings.ai_rate_limit_per_user_hourly,
        used=user_used,
        window=USER_RATE_WINDOW,
        oldest=(
            await analysis_crud.oldest_created_at_since(
                db, user_id=user.id, since=user_since
            )
            if user_used >= settings.ai_rate_limit_per_user_hourly
            else None
        ),
        message=(
            "You are running analyses faster than the coach allows. An analysis "
            "covers twelve weeks of training, so there is little to gain from "
            "another one this soon. Please wait a little and try again."
        ),
    )

    return [global_limit, user_limit]


async def require_ai_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: allow an AI coach run, or refuse with a 429 or a 402.

    Drops into a route in place of `get_current_user` — it returns the same
    `User`, so the handler body does not change. Both the rate limits and the
    plan quota live behind this one dependency deliberately: a route either
    takes `get_current_user` and does not run the model, or takes this and gets
    every control at once. There is no third option to forget half of.

    **The order is rate limits, then quota**, and it is not arbitrary. The rate
    limits describe whether the deployment will spend money on this call at all;
    the quota describes whether this user's plan includes it. Asking someone to
    upgrade — and take their money — for a call that the capacity ceiling is
    about to refuse anyway would be the wrong answer in the most expensive
    possible way.

    **429 and 402 are both refusals and they mean opposite things.** 429 says
    wait, 402 says pay. A user who has spent three free runs is not going too
    fast, and telling them to slow down hides the actual remedy; a user hitting
    a rate limit is not short of money, and offering them an upgrade would sell
    something that does not fix it — premium is exempt from the quota and is not
    exempt from the rate limits. The frontend renders an upgrade prompt for one
    and "try again shortly" for the other, so the two must stay distinguishable.

    The body is a dict rather than a string so the frontend can key off `code`
    instead of parsing prose. `lib/api.ts` already preserves non-string details
    on `ApiError.detail`.
    """
    now = datetime.now(timezone.utc)
    for limit in await ai_rate_limits(db, user=current_user):
        if not limit.exceeded:
            continue

        retry_after = limit.retry_after_seconds(now=now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": limit.code,
                "message": limit.message,
                "retry_after_seconds": retry_after,
            },
            # The header is the half a machine reads. Without it a client that
            # retries has no basis for choosing when, and the usual choice is
            # immediately — which turns one refused request into a hot loop
            # against the endpoint the limit exists to protect.
            headers={"Retry-After": str(retry_after)},
        )

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
    "CAPACITY_ERROR_CODE",
    "GLOBAL_RATE_WINDOW",
    "PREMIUM_STATUSES",
    "QUOTA_ERROR_CODE",
    "RATE_LIMIT_ERROR_CODE",
    "USER_RATE_WINDOW",
    "QuotaState",
    "RateLimit",
    "ai_rate_limits",
    "is_premium",
    "quota_state",
    "require_ai_quota",
]
