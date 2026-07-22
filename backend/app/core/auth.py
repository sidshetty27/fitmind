"""Clerk JWT verification and the `get_current_user` FastAPI dependency.

This is the seam the whole architecture doc hangs on: the frontend attaches a
Clerk session JWT as `Authorization: Bearer <token>`, and every protected route
resolves it here into one of *our* `User` rows.

**Why verify offline against JWKS instead of calling Clerk per request.** Clerk
signs each token with a private RSA key and publishes the matching public keys at
a JWKS URL. Verifying the signature locally proves the token is authentic without
a network hop to Clerk on the hot path — auth stays a CPU-bound signature check.
`PyJWKClient` fetches and caches those public keys, refetching only when it sees
an unfamiliar `kid` (i.e. after Clerk rotates keys).

**Why the dependency returns a `User`, not raw claims.** The rest of the codebase
should never handle a `clerk_id` or a raw token — it deals in internal `users.id`.
Doing the Clerk→user mapping (and just-in-time provisioning) in exactly one place
is what keeps that boundary from leaking everywhere.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import fetch_clerk_user
from app.core.config import settings
from app.crud.user import get_or_create_user_by_clerk_id
from app.db.session import get_db
from app.models.user import User

# `auto_error=False`: we raise our own 401 with a consistent shape instead of
# letting HTTPBearer emit its default. It still registers the scheme with OpenAPI,
# so Swagger shows an "Authorize" button that injects the Bearer header.
_bearer = HTTPBearer(auto_error=False)

# One JWKS client per process, built lazily on first authenticated request so the
# app still boots (and non-auth routes still serve) when Clerk is unconfigured.
_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        jwks_url = settings.effective_clerk_jwks_url
        if not jwks_url:
            # A configuration error, not a client error: the operator forgot to
            # set CLERK_ISSUER. 500 is correct — the request was fine.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Clerk authentication is not configured (set CLERK_ISSUER).",
            )
        # cache_keys keeps fetched signing keys in memory across requests; the
        # client re-fetches automatically on an unknown kid (key rotation).
        _jwk_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwk_client


def _unauthorized(detail: str) -> HTTPException:
    # 401 with WWW-Authenticate is the correct, spec-compliant shape for a bad or
    # missing bearer token, and lets clients distinguish "log in again" from a 403.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _verify_token(token: str) -> dict:
    """Verify a Clerk JWT's signature and standard claims; return its payload.

    Synchronous by design — `PyJWKClient.get_signing_key_from_jwt` may do a
    blocking network fetch on a cache miss, so the caller runs this in a thread
    pool to avoid stalling the event loop.
    """
    client = _get_jwk_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            # Clerk session tokens carry no `aud`; we authorize via `azp` below.
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # Any signature/expiry/issuer failure collapses to a single 401. We never
        # echo the library's message — it can hint at why a forgery failed.
        raise _unauthorized("Invalid or expired token") from exc


def _authorized_party_ok(claims: dict) -> bool:
    allowed = settings.clerk_authorized_parties_list
    if not allowed:
        return True  # check disabled
    return claims.get("azp") in allowed


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated Clerk user into our internal `User` row.

    JIT-provisions the row on first sight so a freshly signed-up user is never
    stuck without one, independent of whether the `user.created` webhook has
    landed yet (see `crud/user.py`).
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated")

    claims = await run_in_threadpool(_verify_token, credentials.credentials)

    if not _authorized_party_ok(claims):
        raise _unauthorized("Untrusted authorized party")

    clerk_id = claims.get("sub")
    if not clerk_id:
        raise _unauthorized("Token missing subject")

    # Email is required by the schema. Prefer a claim (zero-latency, if a JWT
    # template provides it); fall back to the Clerk Backend API only when needed.
    email = claims.get("email")
    name = claims.get("name") or claims.get("full_name")
    if not email:
        clerk_user = await fetch_clerk_user(clerk_id)
        if clerk_user is not None:
            email = clerk_user.email
            name = name or clerk_user.name

    if not email:
        # Actionable server error: the deployment neither puts email in the token
        # nor allows us to fetch it. This is a setup mistake, not a client fault.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Cannot determine user email: add an 'email' claim to the Clerk "
                "JWT template or set CLERK_SECRET_KEY."
            ),
        )

    return await get_or_create_user_by_clerk_id(
        db, clerk_id=clerk_id, email=email, name=name
    )


# A readable alias for route signatures: `user: CurrentUser`.
CurrentUser = User
