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

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import svix
from app.core.config import settings
from app.crud import user as user_crud
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


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
        await user_crud.delete_user_by_clerk_id(db, clerk_id=clerk_id)
    # Any other event type is acknowledged and ignored — Clerk sends many we do
    # not subscribe to logic for, and 204 stops it retrying them.
