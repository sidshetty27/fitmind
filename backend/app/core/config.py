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

    # ---------- Clerk authentication (Phase 4) ----------
    # The backend does NOT talk to Clerk to check a session — it verifies the JWT
    # the frontend sends against Clerk's published public keys (JWKS). That keeps
    # the auth hot path a local signature check, with no per-request round trip to
    # Clerk.
    #
    # `clerk_issuer` is the `iss` claim Clerk stamps into every token — your
    # Frontend API URL, e.g. https://your-app.clerk.accounts.dev (dev) or your
    # custom domain (prod). Find it in Clerk Dashboard → API keys → "Frontend API
    # URL". Left optional so the app (and its tests) still boot without it; the
    # first *authenticated* request then fails loudly if it is missing.
    clerk_issuer: str | None = None

    # JWKS endpoint. Defaults to `{issuer}/.well-known/jwks.json`, which is where
    # Clerk publishes it — only set this to override (e.g. a proxy).
    clerk_jwks_url: str | None = None

    # Optional hardening: the `azp` (authorized party) claim is the origin that
    # requested the token. Restricting it to your known frontends blocks a token
    # minted for some other Clerk app/origin from being replayed here. Comma-
    # separated; empty disables the check.
    clerk_authorized_parties: str = ""

    # Clerk Backend API secret (`sk_...`). Only used as a *fallback*: if a token
    # carries no email claim, we fetch the user's email from Clerk so JIT
    # provisioning can satisfy the NOT NULL `users.email`. Configure a JWT
    # template with an `email` claim to avoid the round trip entirely (see README).
    clerk_secret_key: str | None = None

    # Svix signing secret (`whsec_...`) for the Clerk webhook. Without it the
    # webhook endpoint refuses every delivery — an unverified webhook is an open
    # door to forged user data.
    clerk_webhook_secret: str | None = None

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

    @property
    def effective_clerk_jwks_url(self) -> str | None:
        """Where to fetch Clerk's signing keys, derived from the issuer if unset."""
        if self.clerk_jwks_url:
            return self.clerk_jwks_url
        if self.clerk_issuer:
            return f"{self.clerk_issuer.rstrip('/')}/.well-known/jwks.json"
        return None

    @property
    def clerk_authorized_parties_list(self) -> list[str]:
        """Parse the comma-separated `azp` allow-list into a clean list."""
        return [p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()]


# A single importable settings instance used across the app.
# `database_url` has no default: if it is missing the app refuses to start with a
# loud validation error, rather than booting and failing on the first query.
settings = Settings()
