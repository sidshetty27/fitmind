"""Health endpoint behaviour."""

from httpx import AsyncClient


async def test_liveness_does_not_touch_the_database(client: AsyncClient) -> None:
    """`/health` must stay green even when Postgres is unreachable.

    This is the whole reason liveness and readiness are separate endpoints: if
    `/health` needed the database, a database outage would make the platform
    restart-loop every API container. The test fixture points at an unreachable
    database precisely so this assertion means something.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_503_when_database_is_unreachable(
    client: AsyncClient,
) -> None:
    """`/health/db` must fail loudly, and must not leak the connection string."""
    response = await client.get("/health/db")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["database"] == "unreachable"
    # Only an exception class name — never a message containing host/user/password.
    assert "unreachable" not in body["detail"].lower() or "@" not in body["detail"]
    assert "password" not in body["detail"].lower()


async def test_ping_still_works(client: AsyncClient) -> None:
    """Phase 1's connectivity endpoint must not have regressed."""
    response = await client.get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"message": "pong from FastAPI"}
