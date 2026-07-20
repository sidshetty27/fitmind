"""System endpoints: liveness, readiness (database), and the Phase 1 ping.

The split between `/health` and `/health/db` is deliberate and matters
operationally.

`/health` is a **liveness** probe: is this process running? It must not touch the
database. If it did, a database blip would make the platform's health check fail,
the platform would kill and restart every API container, and a recoverable
database problem would become a full outage — while the restarts pile more
connection attempts onto the struggling database.

`/health/db` is a **readiness/dependency** probe: can this process actually serve
requests? It returns 503 when the database is unreachable, which is what a load
balancer should use to stop routing traffic here, and what a deploy pipeline
should check before promoting a release.
"""

import time

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Intentionally does no I/O."""
    return {"status": "ok", "service": "fitmind-api", "environment": settings.environment}


@router.get("/health/db")
async def health_db(response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Readiness probe: prove we can round-trip a query to Postgres.

    `SELECT 1` is the right check — it verifies the full path (pool → socket →
    TLS → authentication → server executing SQL) while doing no work the database
    has to think about, so it is safe to call every few seconds forever.

    We also report the applied Alembic revision. That answers the question that
    actually causes production confusion — "is this deployment running against
    the schema it expects, or did the migration not run?" — without shelling into
    the box.
    """
    started = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        revision_row = await db.execute(text("SELECT version_num FROM alembic_version"))
        revision = revision_row.scalar_one_or_none()

        return {
            "status": "ok",
            "database": "reachable",
            "latency_ms": latency_ms,
            "migration_revision": revision,
        }
    except SQLAlchemyError as exc:
        # 503, not 500: the API itself is fine, its dependency is not. The
        # distinction is what lets a load balancer retry elsewhere instead of
        # treating this as a bug in the request.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "error",
            "database": "unreachable",
            # Only the exception class, never `str(exc)`: psycopg puts the full
            # DSN — host, user, and sometimes the password — into connection
            # error messages, and this endpoint is unauthenticated.
            "detail": type(exc).__name__,
        }


@router.get("/api/ping")
def ping() -> dict[str, str]:
    """Trivial endpoint the frontend calls in Phase 1 to prove connectivity."""
    return {"message": "pong from FastAPI"}
