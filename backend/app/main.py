"""FastAPI application entry point.

Phase 1 gave us a minimal API the Next.js frontend can reach. Phase 3 adds the
database layer: models, migrations, and a readiness probe. Domain routers (auth,
workouts, AI, billing) mount in later phases.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the engine's lifecycle.

    Nothing to do on startup — the pool connects lazily on first use, so eager
    connecting would only make the app fail to boot during a transient database
    blip. On shutdown we dispose the pool so connections are closed politely
    rather than left for the server to time out.
    """
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)

# CORS: the browser blocks cross-origin requests unless the API explicitly allows
# the frontend origin. We drive the allow-list from settings so prod can differ.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
