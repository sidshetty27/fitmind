"""Auth-gate behaviour that needs no database.

A missing or malformed bearer token is rejected *before* any query runs, so these
assertions hold against the deliberately-unreachable test database — proving the
401 comes from the auth layer, not from a database error masquerading as one.
"""

import pytest
from httpx import AsyncClient

# Every protected route should refuse an unauthenticated caller identically.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/me"),
    ("PATCH", "/api/me"),
    ("GET", "/api/exercises"),
    ("GET", "/api/workouts"),
    ("POST", "/api/workouts"),
    ("GET", "/api/progress"),
    ("PUT", "/api/progress"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
async def test_protected_routes_reject_missing_token(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)
    assert response.status_code == 401
    # Spec-compliant challenge so clients know to re-authenticate.
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_malformed_authorization_header_is_rejected(client: AsyncClient) -> None:
    """A header without the `Bearer` scheme is not a credential."""
    response = await client.get("/api/me", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


async def test_public_routes_need_no_token(client: AsyncClient) -> None:
    """Liveness and ping must stay open — they are not user-scoped."""
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/api/ping")).status_code == 200
