"""Application settings, loaded from environment variables (and a local .env file).

Using pydantic-settings gives us typed, validated config with a single source of
truth. Every deployment environment (local, Railway/Render) sets these vars.
"""

import re

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

    # Optional pattern for origins that cannot be listed literally because their
    # hostname is generated. Vercel is the case this exists for: every branch
    # gets a preview deployment at an origin like
    # `https://fitmind-git-my-branch-myteam.vercel.app`, which no fixed
    # allow-list can contain. Without this, every preview deploy looks fine and
    # fails on its first API call with a CORS error — the branch is "deployed"
    # and unusable, and the same review that would catch it never happens.
    #
    # Matched with `re.fullmatch` by Starlette, so the pattern must describe the
    # whole origin. Anchors are therefore optional; writing them anyway is worth
    # it because the pattern reads as an allow-list rule either way.
    #
    # **The dangerous mistake is breadth, not anchoring.** `.*\.vercel\.app`
    # fullmatches — and hands every Vercel user on earth a credentialed origin
    # against this API. Include the project and team slug so the pattern
    # describes *your* previews:
    #
    #   ^https://fitmind-git-[a-z0-9-]+-myteam\.vercel\.app$
    #
    # `_reject_overly_broad_cors_regex` below refuses the worst of these at boot
    # rather than letting them quietly widen the allow-list.
    cors_origin_regex: str | None = None

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

    # ---------- AI rate limiting (Phase 9) ----------
    # The two limits above and below answer different questions and are not
    # substitutes. `free_daily_ai_analyses` is *pricing*: it decides what a plan
    # includes, and premium is deliberately exempt. These two are *cost control*,
    # and nothing is exempt from them.
    #
    # The distinction matters because the coach is the only endpoint in this app
    # that spends money on each call, and a per-account allowance cannot bound
    # that spend. Signing up is free and unlimited, so an attacker who wants to
    # run up an Anthropic bill does not need to exceed anyone's quota — they need
    # more accounts, and each new account arrives with a fresh allowance. The
    # quota is the wrong shape for the problem entirely.
    #
    # Per user, per hour. Applies to premium too, which is the point: "unlimited"
    # is a plan promise about a day's work, not a licence to run the endpoint in
    # a loop. Also the only thing that catches a client bug retrying forever.
    # Analyses cover a 12-week window, so a second run within the hour reflects
    # almost no new data — 10 is generous for anything a person does deliberately.
    ai_rate_limit_per_user_hourly: int = 10

    # Across every user, per rolling day. This is the ceiling on the bill, and
    # the only control here that an attacker cannot widen by making more
    # accounts. Sized against the free allowance: at the default of 3/day it is
    # roughly 66 fully-active free accounts, comfortably above any real usage
    # this deployment will see and far below a number worth panicking about.
    #
    # Raise it when legitimate traffic approaches it — `/health/db` will not tell
    # you, but a 503-free log full of `ai_capacity_reached` will. Both limits
    # refuse everything at 0, matching `free_daily_ai_analyses`.
    ai_rate_limit_global_daily: int = 200

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

    @field_validator("cors_origin_regex")
    @classmethod
    def _reject_overly_broad_cors_regex(cls, value: str | None) -> str | None:
        """Refuse a preview pattern that is wider than its author meant.

        Two failures, both caught here rather than at the first preflight — a
        CORS mistake is otherwise discovered either never (too broad) or by a
        user (too narrow, or invalid).

        The probes are the point. A pattern is only doing its job if it matches
        this deployment's previews and nothing else, so the check is empirical:
        compile it, then try it against origins that must never be allowed. It
        cannot prove a pattern correct, but it catches the shapes people
        actually write — `.*`, `.*\\.vercel\\.app`, a bare `.+` — each of which
        turns a preview allowance into "any site may call this API with the
        user's credentials".
        """
        if value is None:
            return value

        try:
            pattern = re.compile(value)
        except re.error as exc:
            raise ValueError(f"CORS_ORIGIN_REGEX is not a valid regular expression: {exc}") from exc

        # Origins no correct pattern can match.
        #
        # The fourth is the one that earns this validator. `.*\.vercel\.app`
        # fullmatches it, and that pattern is what someone writes when they mean
        # "our previews" — it reads as scoped and allows every deployment every
        # Vercel user has ever created, each of which can then call this API
        # with a signed-in user's credentials. None of the obvious probes catch
        # it: it is not `evil.example`, and it is a perfectly well-formed
        # `vercel.app` subdomain. It just is not *ours*.
        #
        # The last is suffix confusion: a hostname that ends in an attacker's
        # domain while containing the one being allowed.
        hostile = (
            "https://evil.example",
            "https://vercel.app",
            "https://someone-elses-app.vercel.app",
            "https://fitmind.vercel.app.evil.example",
        )
        matched = [origin for origin in hostile if pattern.fullmatch(origin)]
        if matched:
            raise ValueError(
                f"CORS_ORIGIN_REGEX is too broad — it matches {matched}. "
                "Include the project and team slug so it describes only this "
                "deployment's preview origins, e.g. "
                r"^https://fitmind-git-[a-z0-9-]+-myteam\.vercel\.app$"
            )

        return value

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
