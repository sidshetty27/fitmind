"""`/api/webhooks/clerk` — Clerk → FitMind user synchronisation.

**Why a webhook when JIT provisioning already creates users.** JIT (see
`crud/user.py`) makes the system *correct* — a user always gets a row on their
first authenticated request. The webhook makes it *fresh and complete*:

  - `user.created` pre-provisions the row before the first request, so nothing is
    ever momentarily missing.
  - `user.updated` propagates email/name changes Clerk is authoritative for —
    which JIT (DO NOTHING) deliberately never overwrites.
  - `user.deleted` removes the account and, by DB CASCADE, all its data.

**Why the raw body is read directly.** Svix signs the exact bytes Clerk sent.
Parsing to JSON and re-serialising would reorder keys and break the signature, so
we verify against `await request.body()` first and only then parse.

The endpoint is unauthenticated in the Clerk-JWT sense — Clerk is a server, not a
logged-in user — but it is *authenticated by signature*: without a valid Svix
signature every delivery is rejected, which is what stops anyone POSTing forged
`user.deleted` events.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import stripe_client, svix
from app.core.config import settings
from app.crud import subscription as subscription_crud
from app.crud import user as user_crud
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Stripe statuses where billing has already stopped, so there is nothing for an
# account deletion to cancel. Asking Stripe to cancel one of these is an error
# rather than a no-op, which is why it is checked before calling rather than
# handled after.
_ALREADY_ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})


def _primary_email(data: dict) -> str | None:
    primary_id = data.get("primary_email_address_id")
    for entry in data.get("email_addresses", []):
        if entry.get("id") == primary_id:
            return entry.get("email_address")
    addresses = data.get("email_addresses") or []
    return addresses[0].get("email_address") if addresses else None


def _full_name(data: dict) -> str | None:
    name = f"{data.get('first_name') or ''} {data.get('last_name') or ''}".strip()
    return name or None


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(request: Request) -> None:
    """Receive and apply a Clerk user event. Returns 204 on success."""
    if not settings.clerk_webhook_secret:
        # Refuse rather than silently accept unverified payloads: an unconfigured
        # secret must fail closed, never open.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured",
        )

    payload = await request.body()
    try:
        svix.verify(
            secret=settings.clerk_webhook_secret,
            payload=payload,
            svix_id=request.headers.get("svix-id"),
            svix_timestamp=request.headers.get("svix-timestamp"),
            svix_signature=request.headers.get("svix-signature"),
        )
    except svix.SvixVerificationError as exc:
        # One opaque 400 for every verification failure — never reveal which check
        # failed, or an attacker learns how to shape a forgery.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        ) from exc

    event = json.loads(payload)
    event_type = event.get("type")
    data = event.get("data", {})
    clerk_id = data.get("id")

    if not clerk_id:
        # Signed but malformed — accept (204) so Clerk does not retry forever, but
        # do nothing. Retrying cannot fix a payload with no user id.
        return

    # A session per webhook — these arrive outside any request's DB dependency.
    async with AsyncSessionLocal() as db:
        await _apply_event(db, event_type, clerk_id, data)


async def _cancel_billing(db: AsyncSession, clerk_id: str) -> None:
    """Stop charging a card for an account that is being deleted.

    **Order matters, and it is the whole reason this is a separate function.**
    `subscriptions.user_id` is ON DELETE CASCADE, so the row naming the Stripe
    subscription disappears the instant the user is deleted. Read it after, and
    the subscription keeps billing with nothing left in our database pointing at
    it — the charge would only be discoverable by going through the Stripe
    dashboard by hand.

    **Why a failure here aborts the deletion.** Raising sends a 5xx, Clerk
    retries the `user.deleted` event, and we get another attempt at cancelling.
    The alternative — delete anyway, log the error — destroys the last local
    record of a subscription that is still charging someone for an account they
    closed. Delayed deletion is recoverable and invisible to the user, who can no
    longer sign in either way; a silent recurring charge is neither.
    """
    user = await user_crud.get_user_by_clerk_id(db, clerk_id)
    if user is None:
        return  # already deleted, or never provisioned

    subscription = await subscription_crud.get_by_user_id(db, user_id=user.id)
    if subscription is None or not subscription.stripe_subscription_id:
        return  # free tier, or a customer who never completed checkout

    if subscription.status in _ALREADY_ENDED_STATUSES:
        return  # nothing left to stop

    if not settings.stripe_secret_key:
        # Nothing we can do about it here, but this must not pass unremarked:
        # somebody is about to lose the only local record of a live subscription.
        logger.error(
            "Deleting user %s who has Stripe subscription %s, but STRIPE_SECRET_KEY "
            "is not set — cancel it manually in the Stripe dashboard.",
            clerk_id,
            subscription.stripe_subscription_id,
        )
        return

    await stripe_client.cancel_subscription(subscription.stripe_subscription_id)
    logger.info(
        "Cancelled Stripe subscription %s for deleted user %s",
        subscription.stripe_subscription_id,
        clerk_id,
    )


async def _apply_event(
    db: AsyncSession, event_type: str | None, clerk_id: str, data: dict
) -> None:
    if event_type in ("user.created", "user.updated"):
        email = _primary_email(data)
        if not email:
            return  # cannot upsert a NOT NULL email; JIT will fill it in later
        await user_crud.sync_user_from_clerk(
            db, clerk_id=clerk_id, email=email, name=_full_name(data)
        )
    elif event_type == "user.deleted":
        await _cancel_billing(db, clerk_id)
        await user_crud.delete_user_by_clerk_id(db, clerk_id=clerk_id)
    # Any other event type is acknowledged and ignored — Clerk sends many we do
    # not subscribe to logic for, and 204 stops it retrying them.
