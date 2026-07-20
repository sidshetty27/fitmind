"""Async engine, session factory, and the FastAPI request-scoped session dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# One engine per process. The engine owns the connection pool, so creating them
# per-request (a common early mistake) means never reusing a connection.
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    # Cheap `SELECT 1` before handing out a pooled connection. Supabase (and any
    # cloud Postgres behind a load balancer) will drop idle connections; without
    # pre-ping the first query after an idle period fails instead of transparently
    # reconnecting.
    pool_pre_ping=True,
    connect_args={
        # Supabase's transaction pooler (pgbouncer, port 6543) does not support
        # server-side prepared statements: a statement prepared on one backend is
        # invisible to the next transaction, which lands on a different backend.
        # psycopg3 prepares automatically after a statement is reused 5 times, so
        # this would fail intermittently *under load only* — the worst kind of
        # bug. `None` disables auto-preparation entirely.
        "prepare_threshold": None,
    },
)

# `expire_on_commit=False` matters in async code: the default expires every ORM
# attribute on commit, so touching `user.email` afterwards triggers a lazy
# refresh — which in async SQLAlchemy raises MissingGreenlet rather than quietly
# issuing a query. Keeping objects usable after commit is what route handlers
# almost always want (they still need to serialise the object into a response).
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding one session per request.

    Scope is deliberately the request: a session is a unit of work and an
    identity map, and sharing one across requests would leak one user's objects
    into another's transaction.

    We do NOT commit here. Committing in the dependency makes every handler's
    write implicitly durable, which hides partial writes; handlers commit
    explicitly when their unit of work is complete. The `async with` block always
    closes the session, returning the connection to the pool, and rolls back any
    transaction still open if the handler raised.
    """
    async with AsyncSessionLocal() as session:
        yield session
