"""Workout template tests — schema invariants and the API contract.

Split the same way as the existing suites: assertions that need no database run
unconditionally, and anything requiring real rows opts in via TEST_DATABASE_URL
(see `conftest.py`) so CI stays green without Postgres.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.db.base import Base
from app.models import WorkoutTemplate, WorkoutTemplateExercise
from app.schemas.template import (
    TemplateApply,
    TemplateCreate,
    TemplateExerciseCreate,
    TemplateUpdate,
)

# ---------------------------------------------------------------- schema shape


def test_template_tables_are_registered_on_the_metadata() -> None:
    """A model missing here is invisible to Alembic autogenerate."""
    assert {"workout_templates", "workout_template_exercises"} <= set(
        Base.metadata.tables
    )


def test_templates_cascade_on_account_deletion() -> None:
    """Deleting a user must not leave orphaned templates behind."""
    fk = next(
        fk
        for fk in WorkoutTemplate.__table__.foreign_keys
        if fk.column.table.name == "users"
    )
    assert fk.ondelete == "CASCADE"


def test_template_exercises_cascade_from_their_template() -> None:
    fk = next(
        fk
        for fk in WorkoutTemplateExercise.__table__.foreign_keys
        if fk.column.table.name == "workout_templates"
    )
    assert fk.ondelete == "CASCADE"


def test_catalog_exercises_cannot_be_deleted_out_from_under_a_template() -> None:
    """RESTRICT, matching workout_exercises — retiring a movement is explicit."""
    fk = next(
        fk
        for fk in WorkoutTemplateExercise.__table__.foreign_keys
        if fk.column.table.name == "exercises"
    )
    assert fk.ondelete == "RESTRICT"


def test_template_names_are_unique_per_user_not_globally() -> None:
    """Two users may both have a "Push Day A"; one user having two may not."""
    unique_sets = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in WorkoutTemplate.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("name", "user_id") in unique_sets
    assert ("name",) not in unique_sets


def test_position_is_unique_within_a_template_but_exercise_is_not() -> None:
    """Prescribing the same movement twice in one plan is legitimate."""
    unique_sets = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in WorkoutTemplateExercise.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("position", "template_id") in unique_sets
    assert ("exercise_id", "template_id") not in unique_sets


def test_template_mirrors_workout_exercise_columns() -> None:
    """Applying a template is a field-for-field copy — the shapes must match.

    If someone adds a column to `workout_exercises` and forgets the template side,
    `apply_template` silently stops carrying it. This is the test that notices.
    """
    from app.models import WorkoutExercise

    shared = {"position", "sets", "reps", "weight_kg", "rpe", "notes", "exercise_id"}
    workout_columns = set(WorkoutExercise.__table__.columns.keys())
    template_columns = set(WorkoutTemplateExercise.__table__.columns.keys())
    assert shared <= workout_columns
    assert shared <= template_columns


# ------------------------------------------------------------ schema validation


def test_template_name_is_required_and_bounded() -> None:
    with pytest.raises(ValidationError):
        TemplateCreate(name="")  # empty is not a usable picker label
    with pytest.raises(ValidationError):
        TemplateCreate(name="x" * 201)
    assert TemplateCreate(name="Push Day A").exercises == []


def test_template_exercise_rejects_the_same_values_the_workout_schema_does() -> None:
    """The constraints are mirrored, so the rejections must be too."""
    exercise_id = "00000000-0000-0000-0000-000000000001"

    with pytest.raises(ValidationError):  # sets must be > 0
        TemplateExerciseCreate(exercise_id=exercise_id, sets=0, reps=8)
    with pytest.raises(ValidationError):  # reps must be > 0
        TemplateExerciseCreate(exercise_id=exercise_id, sets=3, reps=0)
    with pytest.raises(ValidationError):  # rpe is 1..10
        TemplateExerciseCreate(exercise_id=exercise_id, sets=3, reps=8, rpe=11)
    with pytest.raises(ValidationError):  # weight cannot be negative
        TemplateExerciseCreate(exercise_id=exercise_id, sets=3, reps=8, weight_kg=-1)

    ok = TemplateExerciseCreate(
        exercise_id=exercise_id, sets=3, reps=8, weight_kg="60.50", rpe="7.5"
    )
    assert ok.weight_kg == Decimal("60.50")
    assert ok.rpe == Decimal("7.5")


def test_position_is_not_client_supplied() -> None:
    """Order comes from array index; a client-sent position would fight the
    uniqueness constraint."""
    assert "position" not in TemplateExerciseCreate.model_fields


def test_template_update_is_partial() -> None:
    """An unset field must stay unset so PATCH cannot null out what it omits."""
    patch = TemplateUpdate(description="Chest and triceps")
    assert patch.model_dump(exclude_unset=True) == {"description": "Chest and triceps"}


def test_apply_requires_the_date_the_session_happened() -> None:
    """A template has no date — that is the whole reason it is not a workout."""
    with pytest.raises(ValidationError):
        TemplateApply()

    applied = TemplateApply(performed_on="2026-07-26")
    # Title omitted means "use the template's name", resolved in the CRUD layer.
    assert applied.title is None
    assert applied.duration_min is None


def test_apply_rejects_a_non_positive_duration() -> None:
    with pytest.raises(ValidationError):
        TemplateApply(performed_on="2026-07-26", duration_min=0)


# ------------------------------------------------------------------ API surface


@pytest.mark.anyio
async def test_template_routes_are_mounted_and_protected(client) -> None:
    """Every template route requires a Clerk session.

    401 (not 404) is the tell that the router is mounted and the auth dependency
    ran before anything touched the database — which matters because the test
    database is deliberately unreachable.
    """
    unauthenticated = [
        ("get", "/api/templates"),
        ("post", "/api/templates"),
        ("get", "/api/templates/00000000-0000-0000-0000-000000000001"),
        ("patch", "/api/templates/00000000-0000-0000-0000-000000000001"),
        ("put", "/api/templates/00000000-0000-0000-0000-000000000001/exercises"),
        ("post", "/api/templates/00000000-0000-0000-0000-000000000001/apply"),
        ("delete", "/api/templates/00000000-0000-0000-0000-000000000001"),
    ]

    for method, path in unauthenticated:
        # `client.request` rather than `client.get(...)` etc: httpx's GET and
        # DELETE helpers do not accept a `json` body, and the write routes need one.
        response = await client.request(method.upper(), path, json={})
        assert response.status_code == 401, (
            f"{method.upper()} {path} -> {response.status_code}"
        )


@pytest.mark.anyio
async def test_templates_appear_in_the_openapi_schema(client) -> None:
    """Swagger is part of the deliverable — the routes must be documented."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/templates" in paths
    assert "/api/templates/{template_id}" in paths
    assert "/api/templates/{template_id}/exercises" in paths
    assert "/api/templates/{template_id}/apply" in paths

    # Applying a template returns the created workout, not the template.
    apply_response = paths["/api/templates/{template_id}/apply"]["post"]["responses"]
    assert "201" in apply_response
