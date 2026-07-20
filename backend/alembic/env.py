"""Alembic environment.

Two deliberate departures from the file `alembic init` generates:

1. **The database URL is not in `alembic.ini`.** It holds a password and the ini
   file is committed. We pull it from `app.core.config` (i.e. the environment),
   which also guarantees migrations and the app agree about which database they
   are pointed at.

2. **Migrations run through a SYNC engine**, while the app runs async. Alembic's
   API is synchronous; the async recipe exists but adds an event-loop dance for
   no benefit, since migrations are a one-shot CLI operation with zero
   concurrency. Using psycopg3 for both means the same DSN string and the same
   driver semantics either way — the only difference is `create_engine` vs
   `create_async_engine`. Note it connects to `effective_migration_url`: DDL must
   bypass Supabase's transaction pooler (see config.py).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings

# Importing the models package registers every model on Base.metadata.
from app.db.base import Base
from app.models import *  # noqa: F401,F403  (import for side effect: model registration)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What autogenerate diffs the live database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting.

    `alembic upgrade head --sql` produces a script a DBA can review and apply by
    hand — the normal path for a change-controlled production database.
    """
    context.configure(
        url=settings.effective_migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = create_engine(
        settings.effective_migration_url,
        # NullPool: a migration run is a single short-lived process. Pooling
        # would just leave connections open at exit.
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without these, autogenerate ignores column type changes and
            # server-default changes — a silent source of drift between the
            # models and the actual schema.
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
