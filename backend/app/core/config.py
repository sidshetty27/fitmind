"""Application settings, loaded from environment variables (and a local .env file).

Using pydantic-settings gives us typed, validated config with a single source of
truth. Every deployment environment (local, Railway/Render) sets these vars.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SQLAlchemy needs a driver in the URL scheme; Supabase hands you a bare
# `postgresql://` DSN. We normalise to psycopg (v3), which we use for BOTH the
# async app engine and the sync Alembic engine — one driver, one wheel, one set
# of connection semantics to reason about.
_PSYCOPG_SCHEME = "postgresql+psycopg://"


def _normalise_pg_url(url: str) -> str:
    """Coerce any Postgres DSN onto the psycopg3 driver.

    Accepts what you actually get from the Supabase dashboard (`postgresql://`)
    and what older tutorials produce (`postgres://`), so nobody has to remember
    to hand-edit the scheme.
    """
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return _PSYCOPG_SCHEME + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App metadata
    app_name: str = "FitMind AI API"
    environment: str = "development"

    # Comma-separated list of origins allowed to call this API (the Next.js app).
    cors_origins: str = "http://localhost:3000"

    # ---------- Database (Phase 3) ----------
    # Runtime connection. On Supabase use the **transaction pooler** (port 6543):
    # it multiplexes many short-lived app connections onto few Postgres backends,
    # which is what a request/response API wants.
    database_url: str

    # Migrations connection. Alembic runs DDL and must NOT go through the
    # transaction pooler — pgbouncer in transaction mode cannot hold the
    # session-level state (advisory locks, `SET`s) that DDL relies on. On
    # Supabase this is the **direct connection** (port 5432) or the session
    # pooler (5432). Defaults to `database_url` for plain local Postgres, where
    # the distinction does not exist.
    migration_database_url: str | None = None

    # Echo every SQL statement to stdout. Invaluable while learning the ORM,
    # far too noisy for production.
    db_echo: bool = False

    # Connection pool sizing. Small on purpose: Supabase's free tier caps total
    # backends, and an API that holds connections open per-request needs far
    # fewer than people assume.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # Recycle below any upstream idle timeout so we never hand out a socket the
    # server has already closed.
    db_pool_recycle_seconds: int = 1800

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _coerce_driver(cls, value: str | None) -> str | None:
        return _normalise_pg_url(value) if value else value

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_migration_url(self) -> str:
        """URL Alembic should use — the direct connection when one is configured."""
        return self.migration_database_url or self.database_url


# A single importable settings instance used across the app.
# `database_url` has no default: if it is missing the app refuses to start with a
# loud validation error, rather than booting and failing on the first query.
settings = Settings()
