"""End-to-end API tests against a real Postgres. Opt-in via TEST_DATABASE_URL.

Matches the repo's existing philosophy (see conftest): the default test run needs
no database, and tests that genuinely require one announce themselves and skip
when it is absent. Point TEST_DATABASE_URL at a *throwaway* database — the schema
is created and dropped around each test.

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fitmind_test pytest

Auth is stubbed by overriding `get_current_user` with a seeded user, so these
tests exercise the routing, CRUD, serialization, and ownership scoping — not Clerk
itself (that path is covered by test_auth.py and by JWKS verification upstream).
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_current_user
from app.core.config import _normalise_pg_url
from app.crud import workout as workout_crud
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Exercise, User
from app.models.enums import Equipment, MuscleGroup

TEST_URL = _normalise_pg_url(os.getenv("TEST_DATABASE_URL", ""))

pytestmark = pytest.mark.skipif(
    not TEST_URL, reason="Set TEST_DATABASE_URL to run integration tests"
)


@pytest.fixture
async def seeded():
    """Fresh schema + one user + one catalog exercise, torn down after."""
    engine = create_async_engine(TEST_URL, connect_args={"prepare_threshold": None})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        user = User(clerk_id="user_test", email="tester@example.com", name="Tester")
        exercise = Exercise(
            name="Barbell Bench Press",
            primary_muscle_group=MuscleGroup.CHEST,
            equipment=Equipment.BARBELL,
            is_compound=True,
        )
        session.add_all([user, exercise])
        await session.commit()
        user_id, exercise_id = user.id, exercise.id

    yield Session, user_id, exercise_id

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def auth_client(seeded):
    """ASGI client wired to the test DB and authenticated as the seeded user."""
    Session, user_id, exercise_id = seeded

    async def _override_get_db():
        async with Session() as session:
            yield session

    async def _override_current_user():
        async with Session() as session:
            return await session.get(User, user_id)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, user_id, exercise_id
    finally:
        app.dependency_overrides.clear()


async def test_me_read_and_update(auth_client) -> None:
    client, _, _ = auth_client

    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "tester@example.com"

    patched = await client.patch(
        "/api/me", json={"goal": "hypertrophy", "height_cm": "180.00"}
    )
    assert patched.status_code == 200
    assert patched.json()["goal"] == "hypertrophy"

    # Persisted, not just echoed back.
    assert (await client.get("/api/me")).json()["goal"] == "hypertrophy"


async def test_exercise_catalog_listing_and_filter(auth_client) -> None:
    client, _, _ = auth_client

    all_ex = await client.get("/api/exercises")
    assert all_ex.status_code == 200
    assert any(e["name"] == "Barbell Bench Press" for e in all_ex.json())

    filtered = await client.get("/api/exercises", params={"muscle_group": "chest"})
    assert len(filtered.json()) == 1
    assert (await client.get("/api/exercises", params={"muscle_group": "back"})).json() == []


async def test_workout_lifecycle(auth_client) -> None:
    client, _, exercise_id = auth_client

    # Create with one exercise.
    created = await client.post(
        "/api/workouts",
        json={
            "performed_on": "2026-07-20",
            "title": "Push day",
            "exercises": [
                {"exercise_id": str(exercise_id), "sets": 3, "reps": 8, "weight_kg": "60.00"}
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    workout_id = body["id"]
    assert body["exercises"][0]["position"] == 0
    assert body["exercises"][0]["exercise"]["name"] == "Barbell Bench Press"

    # List shows it with a count, not the nested sets.
    listed = await client.get("/api/workouts")
    assert listed.status_code == 200
    assert listed.json()[0]["exercise_count"] == 1

    # Patch a scalar field; exercises untouched.
    patched = await client.patch(f"/api/workouts/{workout_id}", json={"title": "Chest day"})
    assert patched.json()["title"] == "Chest day"
    assert len(patched.json()["exercises"]) == 1

    # Replace the exercise list atomically.
    replaced = await client.put(
        f"/api/workouts/{workout_id}/exercises",
        json={"exercises": [
            {"exercise_id": str(exercise_id), "sets": 5, "reps": 5},
            {"exercise_id": str(exercise_id), "sets": 3, "reps": 8},
        ]},
    )
    assert [e["position"] for e in replaced.json()["exercises"]] == [0, 1]

    # Delete → gone.
    assert (await client.delete(f"/api/workouts/{workout_id}")).status_code == 204
    assert (await client.get(f"/api/workouts/{workout_id}")).status_code == 404


async def test_unknown_exercise_is_422(auth_client) -> None:
    client, _, _ = auth_client
    resp = await client.post(
        "/api/workouts",
        json={
            "performed_on": "2026-07-20",
            "exercises": [{"exercise_id": str(uuid.uuid4()), "sets": 3, "reps": 8}],
        },
    )
    assert resp.status_code == 422


async def test_progress_upsert_merges_not_overwrites(auth_client) -> None:
    client, _, _ = auth_client

    first = await client.put("/api/progress", json={"recorded_on": "2026-07-22", "bodyweight_kg": "80.00"})
    assert first.status_code == 200

    # Logging sleep for the same day must not wipe the bodyweight.
    second = await client.put("/api/progress", json={"recorded_on": "2026-07-22", "sleep_hours": "7.5"})
    body = second.json()
    assert body["sleep_hours"] == 7.5
    assert body["bodyweight_kg"] == 80.0  # preserved

    # One row per day, no duplicate.
    listed = await client.get("/api/progress")
    assert len(listed.json()) == 1

    assert (await client.delete("/api/progress/2026-07-22")).status_code == 204
    assert (await client.get("/api/progress/2026-07-22")).status_code == 404


async def test_ownership_is_scoped_to_the_user(seeded) -> None:
    """A workout is invisible to any other user — the 404-not-403 guarantee."""
    Session, owner_id, exercise_id = seeded

    async with Session() as session:
        other = User(clerk_id="user_other", email="other@example.com")
        session.add(other)
        await session.commit()
        other_id = other.id

    from app.schemas.workout import WorkoutCreate

    async with Session() as session:
        created = await workout_crud.create_workout(
            session, user_id=owner_id, data=WorkoutCreate(performed_on="2026-07-20")
        )

    async with Session() as session:
        # Owner sees it; the other user does not.
        assert await workout_crud.get_workout(session, user_id=owner_id, workout_id=created.id)
        assert await workout_crud.get_workout(session, user_id=other_id, workout_id=created.id) is None
