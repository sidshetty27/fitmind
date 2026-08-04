"""`/api/webhooks/stripe` — Stripe → FitMind billing synchronisation.

This endpoint is the **only** writer of subscription status anywhere in the app.
Nothing a logged-in user does can change their own plan; the plan changes when
Stripe says money moved. That is what makes `subscriptions.status` mean "Stripe
agrees this person paid" rather than "some code once set a flag".

**Why every handler re-fetches the subscription.** Each event already contains
the object, so re-fetching looks redundant. It is not: the event carries the
object *as it was when the event fired*, and Stripe both retries deliveries and
makes no ordering guarantee. Applying events as they arrive means a redelivered
`created` can land after an `updated` and downgrade a paying customer. Fetching
the current object instead makes ordering irrelevant — whatever sequence arrives,
we write what is true now, and a duplicate delivery writes the same thing twice.
That is why there is no processed-event table here: idempotency comes from the
shape of the write, not from remembering what we have seen.

**Why failures return 5xx rather than swallowing.** A 2xx tells Stripe the event
is handled and it will never be sent again. Any failure we cannot resolve must
therefore be loud enough for Stripe to retry — silently returning 204 on a failed
fetch would lose that state change permanently.

Like the Clerk webhook, this route is unauthenticated in the session sense and
authenticated by signature: without a valid `Stripe-Signature` every delivery is
rejected, which is what stops anyone POSTing a forged "this user is premium".
"""

import logging

import stripe
from fastapi import APIRouter, HTTPException, Request, status

from app.core import stripe_client
from app.core.config import settings
from app.crud import subscription as subscription_crud
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Events that can change what a user is entitled to.
#
# `checkout.session.completed` is included even though `customer.subscription.
# created` covers the same moment, because it is the one event guaranteed to name
# the checkout we started. The subscription events are the ongoing truth:
# renewals, failed payments, cancellations, and plan changes all arrive as
# `updated`.
#
# Everything else Stripe sends — invoices, payment intents, charges — is
# acknowledged and ignored. Their consequences reach us as a subscription status
# change, which is the only thing we store.
SUBSCRIPTION_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)


def _subscription_id_from(event_type: str, obj: dict) -> str | None:
    """Find the subscription this event is about.

    A checkout session *references* a subscription; a subscription event *is*
    one. A session in `payment` mode references nothing, which is why this can
    legitimately return None.
    """
    if event_type == "checkout.session.completed":
        subscription = obj.get("subscription")
        # Expanded or not, depending on how the session was created.
        if isinstance(subscription, dict):
            return subscription.get("id")
        return subscription
    return obj.get("id")


@router.post("/stripe", status_code=status.HTTP_204_NO_CONTENT)
async def stripe_webhook(request: Request) -> None:
    """Receive a Stripe event and re-sync the subscription it concerns."""
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        # Fail closed, exactly as the Clerk webhook does. An unconfigured secret
        # must never mean "accept anything".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook not configured",
        )

    payload = await request.body()

    try:
        event = stripe_client.verify_event(
            payload, request.headers.get("stripe-signature")
        )
    except stripe.SignatureVerificationError as exc:
        # One opaque 400 for every verification failure — naming which check
        # failed would teach an attacker how to shape a forgery.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload"
        ) from exc

    event_type = event.get("type", "")
    if event_type not in SUBSCRIPTION_EVENTS:
        # Acknowledged so Stripe stops resending. Subscribing to fewer events in
        # the dashboard is the real fix, but an app that 500s on an event it did
        # not ask for is worse than one that ignores it.
        return

    obj = event.get("data", {}).get("object", {}) or {}
    subscription_id = _subscription_id_from(event_type, obj)

    if not subscription_id:
        # A completed checkout that bought no subscription — a one-off payment
        # mode we do not currently use. Nothing to record.
        logger.info("Stripe event %s carried no subscription; ignoring", event_type)
        return

    try:
        subscription = await stripe_client.retrieve_subscription(subscription_id)
    except stripe.StripeError as exc:
        # Do NOT swallow this. Returning 204 here would tell Stripe the event is
        # handled and permanently lose the state change; 503 asks it to retry.
        logger.error(
            "Could not fetch Stripe subscription %s for %s: %s",
            subscription_id,
            event_type,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach Stripe",
        ) from exc

    state = stripe_client.to_state(subscription)

    # A session per webhook — these arrive outside any request's DB dependency.
    async with AsyncSessionLocal() as db:
        updated = await subscription_crud.apply_stripe_state(
            db,
            stripe_customer_id=state.customer_id,
            stripe_subscription_id=state.subscription_id,
            status=state.status,
            price_id=state.price_id,
            current_period_end=state.current_period_end,
            cancel_at_period_end=state.cancel_at_period_end,
        )

    if updated is None:
        # No row for this customer. Not an error: the Stripe account may serve
        # something besides this app, and a customer we never created is not
        # ours to record. There is no user to attach a new row to anyway.
        logger.info(
            "Stripe customer %s is not a FitMind account; ignoring %s",
            state.customer_id,
            event_type,
        )
