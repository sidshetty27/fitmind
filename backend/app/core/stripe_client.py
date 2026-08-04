"""The only module that knows what a Stripe object looks like.

Everything else in the app deals in `SubscriptionState` — a flat, boring record
of the six things we actually store. That indirection is worth one small module
because Stripe's object shape is not stable: `current_period_end` used to live on
the subscription and now lives on its items (see `to_state`). When the next such
move happens, it breaks here, in one function with a test, rather than in
whichever route happened to read the field.

**Why an explicit `StripeClient` rather than the module-level `stripe.api_key`.**
A global would be set once at import and be invisible at the call site, which
makes it awkward to test and easy to leave configured from a previous run. It
would also be shared mutable state in a process serving many requests.

**Why the `v1` namespace.** `client.subscriptions` still works but emits a
deprecation warning in this SDK version; `client.v1.subscriptions` is where the
functionality now lives.

Every network call uses the SDK's `*_async` variants. The synchronous methods on
these same classes would block the event loop for the duration of a call to
Stripe, which on a slow day is the whole request budget.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import stripe

from app.core.config import settings

logger = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a Stripe call is attempted with no secret key set.

    A configuration mistake, not a user error. Callers turn this into a 503 —
    the request was fine, the deployment is not.
    """


@dataclass(frozen=True)
class SubscriptionState:
    """What Stripe says about a subscription, reduced to what we store.

    Deliberately flat and free of Stripe types so the rest of the app never
    imports `stripe` to read a plan.
    """

    customer_id: str
    subscription_id: str
    status: str
    price_id: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool


def _client() -> stripe.StripeClient:
    if not settings.stripe_secret_key:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not set")
    return stripe.StripeClient(api_key=settings.stripe_secret_key)


def _unix_to_utc(value: int | None) -> datetime | None:
    """Stripe sends epoch seconds; the column is `timestamptz`."""
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _id_of(value: Any) -> str | None:
    """Stripe fields hold either an id string or the expanded object.

    Which one you get depends on the `expand` of the call that produced it, so
    reading `.id` unconditionally works right up until an unexpanded response
    arrives and it is a plain string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return getattr(value, "id", None)


def to_state(subscription: Any) -> SubscriptionState:
    """Flatten a Stripe Subscription into the record we persist.

    **`current_period_end` comes from the first subscription item, not the
    subscription.** It was a top-level field for years and is not one any more —
    it moved onto the items, because a subscription with several items can have
    them billing on different cycles. Code written from memory reads
    `subscription.current_period_end`, gets `None`, and silently stores a NULL
    period end; nothing raises, and the settings page just stops saying when the
    plan renews. We sell a single-item subscription, so the first item's period
    is the subscription's period.

    `price_id` comes from the same item for the same reason.
    """
    items = getattr(getattr(subscription, "items", None), "data", []) or []
    first_item = items[0] if items else None

    price_id = _id_of(getattr(first_item, "price", None)) if first_item else None
    period_end = (
        _unix_to_utc(getattr(first_item, "current_period_end", None))
        if first_item
        else None
    )

    if first_item is None:
        # Not fatal — status is what gates access, and it is still correct. But
        # it means the UI cannot say when the plan renews, which is confusing
        # enough to be worth a line in the log.
        logger.warning(
            "Stripe subscription %s has no items; storing no period end",
            getattr(subscription, "id", "<unknown>"),
        )

    return SubscriptionState(
        customer_id=_id_of(getattr(subscription, "customer", None)) or "",
        subscription_id=subscription.id,
        status=subscription.status,
        price_id=price_id,
        current_period_end=period_end,
        cancel_at_period_end=bool(getattr(subscription, "cancel_at_period_end", False)),
    )


def verify_event(payload: bytes, signature: str | None) -> dict:
    """Verify a webhook signature and return the event as a plain dict.

    Raises `stripe.SignatureVerificationError` on anything that fails — a forged
    signature, a mismatched secret, or a timestamp outside the replay tolerance.
    `ValueError` means the body was not JSON at all.

    The raw bytes matter: Stripe signs exactly what it sent, so parsing to JSON
    and re-serialising would reorder keys and invalidate the signature. Same
    constraint as the Clerk/Svix webhook.

    **Why `verify_header` and `json.loads` rather than `construct_event`.** The
    obvious call does both jobs at once, but it returns a `stripe.Event`, and
    that object is not a dict: it has no `.get`, no `.keys`, and raises
    `AttributeError` — not `KeyError` — for an absent field. Handler code written
    against it reads like dict code and is not. `construct_event` also reaches
    for `event.object` to tell v1 events from v2, so a body without that field
    blows up inside the SDK rather than being rejected cleanly as malformed.

    Verifying the signature and then parsing the bytes ourselves gives an
    ordinary nested dict, and matches what the Clerk webhook already does.
    """
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET is not set")

    # Two things `construct_event` does for you that must be done by hand here,
    # both of which fail quietly rather than loudly if forgotten:
    #
    # 1. **Decode to str.** `verify_header` builds the signed payload with
    #    `"%d.%s" % (timestamp, payload)`. Handed bytes, `%s` interpolates their
    #    *repr* — `b'{"id":...}'`, quotes, prefix and all — so the computed
    #    signature never matches and every delivery is rejected as forged. The
    #    error says "no signatures found matching", which reads like a wrong
    #    secret and sends you looking in the wrong place entirely.
    #
    # 2. **Pass `tolerance`.** It defaults to `None` here, which skips the
    #    timestamp check altogether and would accept a captured delivery
    #    replayed from any point in the past.
    stripe.WebhookSignature.verify_header(
        payload.decode("utf-8"),
        signature or "",
        settings.stripe_webhook_secret,
        tolerance=stripe.Webhook.DEFAULT_TOLERANCE,
    )

    return json.loads(payload)


async def retrieve_subscription(subscription_id: str) -> Any:
    """Fetch the canonical subscription. The webhook's source of truth.

    Called even though the event already carries a subscription object, because
    the event carries the object *as it was when the event fired*. Stripe retries
    and does not promise ordering, so a redelivered older event would otherwise
    overwrite newer state. Re-fetching means whatever order events arrive in, we
    always write what is true now.
    """
    return await _client().v1.subscriptions.retrieve_async(subscription_id)


async def cancel_subscription(subscription_id: str) -> None:
    """Cancel immediately, ending the billing relationship now rather than at
    the period end.

    Used when a FitMind account is deleted: there is no product left to deliver,
    so continuing to charge would be indefensible regardless of what was paid
    for. An already-cancelled subscription is treated as success — Stripe's
    error for it is a description of the state we wanted.
    """
    try:
        await _client().v1.subscriptions.cancel_async(subscription_id)
    except stripe.InvalidRequestError as exc:
        message = str(exc).lower()
        if "no such subscription" in message or "canceled" in message:
            logger.info(
                "Subscription %s was already gone at Stripe; nothing to cancel",
                subscription_id,
            )
            return
        raise


__all__ = [
    "StripeNotConfigured",
    "SubscriptionState",
    "cancel_subscription",
    "retrieve_subscription",
    "to_state",
    "verify_event",
]
