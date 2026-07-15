"""FastAPI application entry point.

Phase 1 goal: a minimal, correctly-configured API that the Next.js frontend can
reach. Auth, database, AI, and billing routers are mounted in later phases.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

# CORS: the browser blocks cross-origin requests unless the API explicitly allows
# the frontend origin. We drive the allow-list from settings so prod can differ.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness probe used by deploy platforms and our own smoke tests."""
    return {"status": "ok", "service": "fitmind-api", "environment": settings.environment}


@app.get("/api/ping", tags=["system"])
def ping() -> dict[str, str]:
    """Trivial endpoint the frontend calls in Phase 1 to prove connectivity."""
    return {"message": "pong from FastAPI"}
