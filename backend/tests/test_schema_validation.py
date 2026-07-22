"""Request-schema validation — the edge that turns bad input into a clean 422.

These mirror the database CHECK constraints. The DB remains the authoritative
guard; this layer just rejects the obvious violations early, with a field-level
message, instead of surfacing an opaque IntegrityError.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.progress import ProgressUpsert
from app.schemas.workout import WorkoutExerciseCreate


def _wx(**overrides):
    base = dict(exercise_id=uuid.uuid4(), sets=3, reps=8)
    base.update(overrides)
    return WorkoutExerciseCreate(**base)


def test_valid_workout_exercise_is_accepted() -> None:
    wx = _wx(weight_kg=60, rpe=8)
    assert wx.sets == 3 and wx.reps == 8


@pytest.mark.parametrize("field,value", [("sets", 0), ("reps", 0), ("sets", -1)])
def test_sets_and_reps_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _wx(**{field: value})


def test_rpe_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _wx(rpe=11)
    with pytest.raises(ValidationError):
        _wx(rpe=0)


def test_negative_weight_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _wx(weight_kg=-5)


def test_bodyweight_movement_allows_null_weight() -> None:
    """NULL weight is valid — it means 'no external load', not zero."""
    assert _wx(weight_kg=None).weight_kg is None


def test_progress_sleep_hours_bounded_to_a_day() -> None:
    with pytest.raises(ValidationError):
        ProgressUpsert(recorded_on="2026-07-22", sleep_hours=25)


def test_progress_calories_non_negative() -> None:
    with pytest.raises(ValidationError):
        ProgressUpsert(recorded_on="2026-07-22", calories=-100)
