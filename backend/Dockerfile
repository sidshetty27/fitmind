# The FitMind API container.
#
# Deliberately host-agnostic. Render is what builds it today, but nothing in
# here knows that: the only contract with the platform is the `PORT` environment
# variable, which Render, Railway, Fly, and Cloud Run all set. Moving hosts is
# then a dashboard change rather than a rewrite, which is the whole reason this
# is a Dockerfile instead of a Render-native Python service.

# Pinned to 3.11 because that is what `.github/workflows/ci.yml` runs. A
# container on a different interpreter than the one the suite passed on is a
# discrepancy you discover in production, not in CI.
FROM python:3.11-slim

# PYTHONUNBUFFERED is the one that actually matters here: stdout is block
# buffered when it is not a TTY, so without it the platform's log tail arrives
# in bursts and — the case you care about — a crash loses the last few lines
# that would have explained it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No `apt-get` step, which is worth stating because its absence looks like an
# oversight: `psycopg[binary]` vendors its own libpq and `cryptography` ships
# manylinux wheels, so every dependency installs from a wheel and needs no
# compiler. Drop the `[binary]` extra from requirements.txt and that stops being
# true — you would then need `build-essential` and `libpq-dev` right here.

# Requirements before source, so editing application code reuses the cached
# dependency layer instead of reinstalling on every deploy.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root. Nothing in the app writes to disk (the filesystem is ephemeral
# anyway), so there is no reason for the process to be able to.
RUN useradd --create-home --uid 10001 fitmind

# `alembic.ini` and `alembic/` come along because the entrypoint runs migrations
# — see docker-entrypoint.sh for why that happens at start rather than in a
# pre-deploy step. `.dockerignore` keeps tests, .env, and the local venv out.
COPY --chown=fitmind:fitmind . .

USER fitmind

# Documentation only — the real port is $PORT at runtime. Left at the local
# default so `docker run -p 8000:8000` behaves the way the README implies.
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
