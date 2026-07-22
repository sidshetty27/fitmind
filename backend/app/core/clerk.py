"""Thin Clerk Backend API client — used only where JWT verification is not enough.

Almost everything about auth is done *offline* by verifying the session JWT's
signature (see `app.core.auth`); this module is the small set of cases that need
to actually call Clerk:

  - Fetching a user's email when the session token does not carry it, so
    just-in-time provisioning can satisfy the NOT NULL `users.email`. This is a
    cold-path fallback: configure a JWT template with an `email` claim (see the
    backend README) and it is never hit.

It deliberately does not wrap the whole Clerk API — only what the app needs.
"""

from __future__ import annotations

import httpx

from app.core.config import settings

_CLERK_API_BASE = "https://api.clerk.com/v1"


class ClerkUser:
    """The handful of Clerk user fields the app cares about."""

    __slots__ = ("email", "name")

    def __init__(self, email: str | None, name: str | None) -> None:
        self.email = email
        self.name = name


def _extract_primary_email(payload: dict) -> str | None:
    """Pull the *primary* verified email out of a Clerk user object.

    Clerk returns a list of email addresses plus a `primary_email_address_id`
    pointing at the canonical one. Grabbing `email_addresses[0]` would be wrong
    the moment a user adds a second address.
    """
    primary_id = payload.get("primary_email_address_id")
    for entry in payload.get("email_addresses", []):
        if entry.get("id") == primary_id:
            return entry.get("email_address")
    # Fall back to the first address if Clerk ever omits the primary pointer.
    addresses = payload.get("email_addresses") or []
    return addresses[0].get("email_address") if addresses else None


def _extract_name(payload: dict) -> str | None:
    first = payload.get("first_name") or ""
    last = payload.get("last_name") or ""
    full = f"{first} {last}".strip()
    return full or None


async def fetch_clerk_user(clerk_id: str) -> ClerkUser | None:
    """Load a user from Clerk's Backend API. Returns None if not configured/found.

    Requires `CLERK_SECRET_KEY`. Kept resilient on purpose: any transport or
    decode error returns None rather than raising, because the caller (JIT
    provisioning) has its own way to report "could not determine email" with a
    developer-actionable message, and a Clerk outage should surface as that, not
    as an opaque 502 from deep in a dependency.
    """
    if not settings.clerk_secret_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(
                f"{_CLERK_API_BASE}/users/{clerk_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            )
        if response.status_code != 200:
            return None
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    return ClerkUser(email=_extract_primary_email(payload), name=_extract_name(payload))
