"""ai_analyses.created_at index — for the global AI rate limit

Revision ID: 0006_ai_analyses_created_at_idx
Revises: 0005_subscriptions
Create Date: 2026-08-26

Purely additive: one index, no table or column touched. Safe to apply to a live
database, and safe to leave in place under a code rollback — the old code simply
does not use it. That is the property `docs/deployment.md` relies on when it says
a rollback reverts code and not schema.

**Why a second index on a table that already has one.** The existing index leads
with `user_id`, which serves every query scoped to an owner. The global rate
limit is the first query in this app with no owner — `count(*)` over the last
day across all users — and a composite index cannot answer a range scan on its
second column. Without this it reads the whole table, on a query that now runs
before every coach request.

Deliberately a plain CREATE INDEX rather than CONCURRENTLY. Concurrent index
builds cannot run inside a transaction, and Alembic wraps each migration in one;
opting out means handling the failure modes of a build that can leave an invalid
index behind. The table holds one row per coach run and the lock is measured in
milliseconds at this size. Revisit at a scale this deployment does not have.

The revision id is abbreviated (`_idx`, not `_index`) because it has to fit
`alembic_version.version_num`, which Alembic creates as VARCHAR(32) and this
project does not override. The unabbreviated name was 33 characters: the index
was created, stamping the version failed, the transaction rolled back, and
`alembic upgrade head` exited non-zero — so this migration could not apply to
any database, new or existing. Keep new revision ids under 32 characters;
`tests/test_migrations.py` fails the build if one is not.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_ai_analyses_created_at_idx"
down_revision: str | None = "0005_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_analyses_created_at",
        "ai_analyses",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_analyses_created_at", table_name="ai_analyses")
