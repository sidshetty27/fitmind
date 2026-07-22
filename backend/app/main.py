"""FastAPI application entry point.

Phase 1 gave us a minimal API the Next.js frontend can reach. Phase 3 added the
database layer: models, migrations, and a readiness probe. Phase 4 mounts the core
domain: Clerk-authenticated CRUD for the profile, workouts, progress, and the
read-only exercise catalog, plus the Clerk user-sync webhook. AI and billing
routers mount in later phases.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import exercises, health, me, progress, webhooks, workouts
from app.core.config import settings
from app.db.session import engine

# On Windows, Python's default asyncio loop is the ProactorEventLoop, which
# psycopg3's async driver refuses to run on ("Psycopg cannot use the
# 'ProactorEventLoop'"). The SelectorEventLoop is compatible. We set the policy at
# import time — before uvicorn creates the event loop — so local Windows dev works
# against Postgres. It is a no-op on the Linux hosts we deploy to (Railway/Render),
# where the default loop already works, so production behaviour is unchanged.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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


app = FastAPI(title=settings.app_name, version="0.4.0", lifespan=lifespan)

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
app.include_router(me.router)
app.include_router(exercises.router)
app.include_router(workouts.router)
app.include_router(progress.router)
app.include_router(webhooks.router)
