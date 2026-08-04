"""Shapes for the billing endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CheckoutSessionRead(BaseModel):
    """Where to send the browser to complete a purchase.

    Only a URL, deliberately. Checkout is hosted by Stripe, so the frontend's
    entire job is `window.location.href = url` — it never handles a card, a
    payment intent, or a client secret, and there is no Stripe.js to load.
    """

    url: str


class SubscriptionRead(BaseModel):
    """What the app is allowed to do, and what to tell the user about their plan.

    Returned by `GET /api/me/subscription`, which is the single source both the
    settings page and the Coach page read. One endpoint rather than two means the
    two screens can never disagree about whether someone is premium.

    **`premium` is the answer, not `status`.** Clients must branch on this and
    never re-derive entitlement from the status string: the rules for what counts
    as paid (`past_due` still does, for instance) live in `core/entitlements.py`
    and must have exactly one implementation.
    """

    premium: bool

    # Stripe's raw status, or None for a user who never subscribed. Present for
    # display and support ("your payment failed"), not for decisions.
    status: str | None = None

    # None when the plan does not renew — free tier, or a cancelled subscription
    # that has already lapsed.
    current_period_end: datetime | None = None

    # True when the user has cancelled but paid through the period, which is the
    # difference between "renews on the 3rd" and "ends on the 3rd". The status
    # stays `active` throughout, so without this the page would tell someone who
    # just cancelled that their plan renews.
    cancel_at_period_end: bool = False

    # Whether this deployment can sell anything at all. False when Stripe is
    # unconfigured, and the UI hides the upgrade path rather than offering a
    # button that cannot work.
    billing_enabled: bool = False

    # Whether the user has a Stripe customer record, and so whether the billing
    # portal can be opened for them. A free user who never started checkout has
    # nothing to manage.
    has_billing_account: bool = False

    # --- AI coach allowance ---
    # Included here rather than on a separate endpoint because it is the same
    # question from the user's point of view: what does my plan let me do today.
    ai_limit: int
    ai_used: int
    # -1 means unlimited, matching `QuotaState.remaining`.
    ai_remaining: int
    # When the oldest run in the rolling window expires. Only set when the
    # allowance is spent — there is nothing to wait for otherwise.
    ai_resets_at: datetime | None = None


__all__ = ["CheckoutSessionRead", "SubscriptionRead"]
