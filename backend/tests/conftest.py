"""Shared test fixtures.

The environment is set here, before anything imports `app.*`. `Settings()` is
instantiated at import time in `app.core.config`, so setting `DATABASE_URL` any
later would be too late.

By default the tests point at a deliberately unreachable database. That is not a
workaround — it is what lets the readiness endpoint's *failure* path be tested
deterministically in CI, with no Postgres and no network. Tests that need a real
database opt in by setting TEST_DATABASE_URL and are skipped otherwise.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://unreachable:unreachable@127.0.0.1:1/nonexistent"
)
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
async def client() -> AsyncClient:
    """In-process HTTP client — no uvicorn, no port, no flakiness."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client
