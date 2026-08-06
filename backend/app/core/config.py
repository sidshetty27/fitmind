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

    # ---------- AI coach (Phase 7) ----------
    # Optional on purpose. The coach computes its findings deterministically from
    # logged workouts; the model only phrases them. With no key the endpoint still
    # returns findings, so the feature degrades to "no coaching voice" rather than
    # to an error — and local development needs no billing account.
    anthropic_api_key: str | None = None

    # Pinned rather than defaulted in code so an upgrade is a config change with
    # an audit trail: `ai_analyses.model` records which model wrote each note.
    anthropic_model: str = "claude-opus-5"

    # How much of the user's history the coach reasons over. Matches the Progress
    # page's default so the two never disagree about what "recently" means.
    coach_window_weeks: int = 12

    # ---------- Billing (Phase 8) ----------
    # Optional, for the same reason the Clerk and Anthropic keys are: the app must
    # boot and the test suite must run without a Stripe account. With billing
    # unconfigured every user is treated as free tier and the checkout routes
    # refuse politely — the app does not break, it just has nothing to sell.
    #
    # The API key this backend authenticates with. Named for the slot rather than
    # the key type: an account secret key (`sk_...`) works, but the right thing
    # to put here is a **restricted key** (`rk_...`) scoped to the four
    # permissions this app actually uses — see `.env.example` for the list, and
    # `stripe_client.py` for the five calls it is derived from.
    #
    # The distinction is worth the sentence because the two are interchangeable
    # at this line and very different if leaked: an `sk_` can refund charges and
    # read every customer on the account, while a correctly scoped `rk_` cannot.
    #
    # The publishable key is absent on purpose: Checkout is hosted, so the
    # browser is redirected to a URL this backend creates and Stripe.js is never
    # loaded. One less key to leak.
    stripe_secret_key: str | None = None

    # Signing secret (`whsec_...`) for /api/webhooks/stripe. Like its Clerk
    # counterpart, missing means the endpoint rejects every delivery rather than
    # trusting an unverified one.
    stripe_webhook_secret: str | None = None

    # The Price the upgrade button buys (`price_...`, not the Product id). Pinned
    # in config so changing what premium costs is a config change, and so the
    # webhook can tell the subscription we sold from one created elsewhere.
    stripe_price_id: str | None = None

    # Path to a CA bundle for Stripe API calls. Almost always unset.
    #
    # The Stripe SDK does not use the system trust store. It ships its own CA
    # bundle and passes it as `cafile=`, which overrides `SSL_CERT_FILE` and
    # `REQUESTS_CA_BUNDLE` rather than being overridden by them. On a machine
    # whose antivirus intercepts HTTPS (Norton, Kaspersky, a corporate proxy),
    # the interceptor's root is in the system store but not in Stripe's bundle,
    # so **only** Stripe calls fail, with `CERTIFICATE_VERIFY_FAILED`, while
    # Clerk and Anthropic work normally.
    #
    # That split is what makes it worth a setting rather than a README note. The
    # failure looks like a bad API key — checkout 500s the moment a key is first
    # used — and the traceback is thirty frames of httpx and httpcore before the
    # word "certificate" appears. Anyone hitting it goes and re-reads their key.
    #
    # Point this at a bundle that includes the interceptor's root to fix it.
    # Leave it unset in production: a deployed Linux host has no interceptor, and
    # the SDK's own bundle is the correct thing to trust there.
    stripe_ca_bundle: str | None = None

    # Where Stripe returns the user after checkout or the billing portal. Separate
    # from `cors_origins` deliberately: that is a security allow-list which may
    # hold several entries, while this is the one canonical place to send someone
    # back to, and picking "the first CORS origin" would be a silent guess.
    frontend_url: str = "http://localhost:3000"

    # Free-tier allowance for AI coach runs, over a rolling 24 hours (see
    # `crud.ai_analysis.count_today`). Config rather than a constant so the
    # business decision can be retuned without a code deploy. Premium is unlimited.
    free_daily_ai_analyses: int = 3

    @property
    def ai_enabled(self) -> bool:
        """Whether a narrative can be generated at all."""
        return bool(self.anthropic_api_key)

    @property
    def billing_enabled(self) -> bool:
        """Whether a subscription can actually be sold.

        Both halves are required: a key with no price has nothing to charge for,
        and a price with no key cannot be charged. Read this before offering an
        upgrade anywhere, so an unconfigured deployment shows no dead buttons.
        """
        return bool(self.stripe_secret_key and self.stripe_price_id)

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
