"""Migration metadata — the constraints Alembic enforces at runtime, not at import.

A migration is the one artefact in this project that no test exercised and CI
never ran: the suite builds its schema from the models, and the Docker job sets
`RUN_MIGRATIONS=false` because it has no database. That leaves the first real
execution of a migration to be the production deploy, which is the worst place
to discover a defect in one.

These tests check the properties that can be checked without a database. They
exist because one of them shipped broken: `0006`'s revision id was 33 characters
against the VARCHAR(32) column Alembic creates for `alembic_version.version_num`,
so the migration created its index, failed to stamp the version, rolled back,
and exited non-zero. It could not apply to *any* database — new or existing —
and nothing in 224 passing tests or a green CI run said so.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

# Alembic's default width for `alembic_version.version_num`. Overridable via
# `version_table_column_length` in env.py; this project does not override it, so
# the default is the real constraint and the test asserts against the default.
VERSION_NUM_MAX_LENGTH = 32

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _revisions():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return list(ScriptDirectory.from_config(config).walk_revisions())


def test_revision_ids_fit_the_version_table_column():
    """Every revision id must fit the column Alembic stamps it into.

    The failure this catches is invisible until the migration runs: the id is a
    plain string everywhere else — in the file, in `down_revision`, in the
    history graph — and only the UPDATE against `alembic_version` truncates. A
    too-long id therefore passes import, passes `alembic history`, and fails on
    the deploy.
    """
    too_long = {
        script.revision: len(script.revision)
        for script in _revisions()
        if len(script.revision) > VERSION_NUM_MAX_LENGTH
    }
    assert not too_long, (
        f"Revision ids exceed alembic_version.version_num "
        f"(VARCHAR({VERSION_NUM_MAX_LENGTH})): {too_long}. "
        "Shorten the id — the migration cannot be stamped, so it cannot apply "
        "to any database."
    )


def test_migration_history_is_linear():
    """One head, no branches.

    `docker-entrypoint.sh` runs `alembic upgrade head` (singular). Two heads
    make that command ambiguous and it fails at deploy time, which is the same
    place and the same blast radius as the defect above.
    """
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"Expected exactly one migration head, found {heads}"


@pytest.mark.parametrize("script", _revisions(), ids=lambda s: s.revision)
def test_every_migration_has_a_downgrade(script):
    """A migration with no `downgrade()` is a one-way door.

    `docs/deployment.md` tells you to write the downgrade path when a migration
    is the thing to roll back. That advice only holds if the path exists.
    """
    source = Path(script.path).read_text(encoding="utf-8")
    assert "def downgrade()" in source, f"{script.revision} has no downgrade()"
    body = source.split("def downgrade()", 1)[1]
    assert "pass" not in body.split("\n\n", 1)[0] or "op." in body, (
        f"{script.revision} has an empty downgrade()"
    )
