#!/bin/sh
# Apply migrations, then serve.
#
# **Why migrations run here and not in a pre-deploy step.** Render's
# `preDeployCommand` is the right home for this — it runs once per deploy,
# before any new instance takes traffic, and a failure aborts the deploy while
# the old version keeps serving. It is also paid-plans-only, and this project
# deploys on the free instance type. Running it at container start is the
# version of that which works on free:
#
#   - `set -e` means a failed migration exits non-zero before uvicorn ever
#     starts, so the deploy fails rather than serving against a schema the code
#     does not expect. That is the property actually worth having.
#   - `alembic upgrade head` is a no-op at head, so the repeat runs on every
#     cold start cost a connection and a version check, not a re-migration.
#
# What it gives up: with more than one instance, several containers can start
# concurrently and race on the same DDL. Free tier runs exactly one, so it
# cannot happen here — but this is the line to revisit before scaling up, and
# the fix is to move the command to `preDeployCommand` in render.yaml (already
# written there, commented out) rather than to add locking.
#
# Set RUN_MIGRATIONS=false to skip — which is what you do once you have moved
# to a pre-deploy step, so the two do not both run.
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> alembic upgrade head"
    # Connects to MIGRATION_DATABASE_URL when set, falling back to DATABASE_URL
    # (app/core/config.py: effective_migration_url). On Supabase these must
    # differ: DDL cannot run through the transaction pooler.
    alembic upgrade head
fi

# 0.0.0.0, not the 127.0.0.1 that run.py uses: inside a container, localhost is
# reachable only from that container, so binding it makes the platform's health
# check fail with nothing in the logs to explain why.
#
# One worker, deliberately. The free instance is 0.1 CPU / 512MB; a second
# worker would contend for the same tenth of a core and double the memory
# floor. Scale by raising the instance type first, workers second.
#
# --proxy-headers so the app sees the client's scheme and IP from the platform
# load balancer rather than the balancer's own. --forwarded-allow-ips=* is safe
# precisely because that balancer is the only route in: nothing else can reach
# the container to forge the header.
echo "==> uvicorn on 0.0.0.0:${PORT:-8000}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips="*"
