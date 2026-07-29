"""Training-analysis tests — the maths, with no database in sight.

Everything here runs unconditionally. That is the point of keeping
`app.analysis.metrics` pure and the series-shaping in `_build_history` free of
the session: the arithmetic that plateau detection and every chart depend on is
verified in the default suite, not behind the `TEST_DATABASE_URL` opt-in that
`test_api_integration.py` needs.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.analysis import metrics
from app.crud.analysis import (
    _build_history,
    _build_record,
    _session_volumes,
    _week_start,
    window_start,
)
from app.schemas.analysis import ExerciseSessionPoint

# ------------------------------------------------------------- estimated 1RM


def test_single_rep_is_returned_unchanged() -> None:
    """A 1-rep set is the measured max — scaling it by Epley's 1.033 would be wrong."""
    assert metrics.estimate_one_rm(Decimal("100"), 1) == Decimal("100.00")


def test_epley_formula() -> None:
    # 100 x (1 + 5/30) = 116.666... -> 116.67 half-up
    assert metrics.estimate_one_rm(Decimal("100"), 5) == Decimal("116.67")
    # 60 x (1 + 10/30) = 80
    assert metrics.estimate_one_rm(Decimal("60"), 10) == Decimal("80.00")


def test_more_reps_estimates_a_higher_max_at_equal_load() -> None:
    assert metrics.estimate_one_rm(Decimal("80"), 8) > metrics.estimate_one_rm(
        Decimal("80"), 3
    )


@pytest.mark.parametrize("weight", [None, Decimal("0")])
def test_bodyweight_has_no_one_rm(weight: Decimal | None) -> None:
    """No external load means nothing to extrapolate — None, never 0."""
    assert metrics.estimate_one_rm(weight, 8) is None


@pytest.mark.parametrize("reps", [0, -1, metrics.MAX_RELIABLE_REPS + 1, 30])
def test_reps_outside_the_reliable_range_give_no_estimate(reps: int) -> None:
    assert metrics.estimate_one_rm(Decimal("100"), reps) is None


def test_the_reliable_boundary_itself_is_included() -> None:
    assert metrics.estimate_one_rm(Decimal("100"), metrics.MAX_RELIABLE_REPS) is not None


# ------------------------------------------------------------------- volume


def test_volume_is_sets_times_reps_times_weight() -> None:
    assert metrics.entry_volume(3, 10, Decimal("62.5")) == Decimal("1875.00")


@pytest.mark.parametrize("weight", [None, Decimal("0")])
def test_bodyweight_volume_is_none_not_zero(weight: Decimal | None) -> None:
    """Zero would drag every average down; None is skipped by the callers."""
    assert metrics.entry_volume(3, 10, weight) is None


def test_total_reps_is_defined_for_bodyweight_work() -> None:
    """Load can be absent; work done cannot. This is what keeps a dips-only week
    from charting as an empty one."""
    assert metrics.total_reps(4, 12) == 48


# -------------------------------------------------------------- best of many


def test_best_one_rm_takes_the_top_set_not_the_last_or_the_mean() -> None:
    entries = [
        (Decimal("60"), 10),  # warm-up      -> 80.00
        (Decimal("100"), 3),  # top set      -> 110.00
        (Decimal("80"), 8),   # back-off     -> 101.33
    ]
    assert metrics.best_estimated_one_rm(entries) == Decimal("110.00")


def test_best_one_rm_of_only_bodyweight_entries_is_none() -> None:
    assert metrics.best_estimated_one_rm([(None, 10), (None, 8)]) is None


def test_best_one_rm_ignores_unusable_entries_among_usable_ones() -> None:
    assert metrics.best_estimated_one_rm(
        [(None, 8), (Decimal("90"), 40), (Decimal("70"), 5)]
    ) == Decimal("81.67")


# --------------------------------------------------------------- percent change


def test_percent_change_is_signed() -> None:
    assert metrics.percent_change(Decimal("100"), Decimal("110")) == Decimal("10.00")
    # A regression is a real finding, not something to clamp to zero.
    assert metrics.percent_change(Decimal("100"), Decimal("90")) == Decimal("-10.00")


@pytest.mark.parametrize(
    ("earlier", "later"),
    [(None, Decimal("100")), (Decimal("100"), None), (Decimal("0"), Decimal("100"))],
)
def test_percent_change_guards_missing_and_zero_baselines(
    earlier: Decimal | None, later: Decimal | None
) -> None:
    assert metrics.percent_change(earlier, later) is None


# ----------------------------------------------------------------- week buckets


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 7, 27), date(2026, 7, 27)),  # a Monday is its own bucket
        (date(2026, 7, 28), date(2026, 7, 27)),  # Tuesday
        (date(2026, 8, 2), date(2026, 7, 27)),   # Sunday still belongs to it
        (date(2026, 8, 3), date(2026, 8, 3)),    # next Monday opens a new bucket
    ],
)
def test_weeks_bucket_from_monday(day: date, expected: date) -> None:
    assert _week_start(day) == expected


# --------------------------------------------------------------- history shape


def _point(
    performed_on: date,
    weight: Decimal | None,
    reps: int,
    *,
    sets: int = 3,
    workout_id: uuid.UUID | None = None,
) -> ExerciseSessionPoint:
    return ExerciseSessionPoint(
        workout_id=workout_id or uuid.uuid4(),
        performed_on=performed_on,
        sets=sets,
        reps=reps,
        weight_kg=weight,
        volume_kg=metrics.entry_volume(sets, reps, weight),
        estimated_one_rm=metrics.estimate_one_rm(weight, reps),
        total_reps=metrics.total_reps(sets, reps),
    )


def test_history_reports_best_and_signed_trend() -> None:
    history = _build_history(
        uuid.uuid4(),
        "Barbell Bench Press",
        [
            _point(date(2026, 6, 1), Decimal("60"), 5),   # 70.00
            _point(date(2026, 6, 8), Decimal("65"), 5),   # 75.83
            _point(date(2026, 6, 15), Decimal("70"), 5),  # 81.67
        ],
    )
    assert history.best_estimated_one_rm == Decimal("81.67")
    assert history.one_rm_change_pct == Decimal("16.67")
    assert history.session_count == 3


def test_history_trend_spans_estimable_points_when_the_window_ends_bodyweight() -> None:
    """The window opening or closing on an unusable set must not erase a real trend."""
    history = _build_history(
        uuid.uuid4(),
        "Barbell Bench Press",
        [
            _point(date(2026, 6, 1), None, 10),           # no estimate
            _point(date(2026, 6, 8), Decimal("60"), 5),   # 70.00
            _point(date(2026, 6, 15), Decimal("70"), 5),  # 81.67
            _point(date(2026, 6, 22), Decimal("50"), 30), # reps beyond reliable range
        ],
    )
    assert history.one_rm_change_pct == Decimal("16.67")


def test_history_with_one_estimable_point_has_no_trend() -> None:
    """One point is a reading, not a direction."""
    history = _build_history(
        uuid.uuid4(), "Dip", [_point(date(2026, 6, 1), Decimal("20"), 8)]
    )
    assert history.best_estimated_one_rm is not None
    assert history.one_rm_change_pct is None


def test_bodyweight_only_history_still_counts_sessions() -> None:
    history = _build_history(
        uuid.uuid4(),
        "Pull-up",
        [_point(date(2026, 6, 1), None, 8), _point(date(2026, 6, 8), None, 10)],
    )
    assert history.session_count == 2
    assert history.best_estimated_one_rm is None
    assert history.one_rm_change_pct is None


def test_two_movements_in_one_session_count_as_one_session() -> None:
    """A second bench slot in the same workout is legitimate training, and the
    model deliberately allows it — it must not inflate the session count."""
    same_workout = uuid.uuid4()
    history = _build_history(
        uuid.uuid4(),
        "Barbell Bench Press",
        [
            _point(date(2026, 6, 1), Decimal("60"), 5, workout_id=same_workout),
            _point(date(2026, 6, 1), Decimal("50"), 8, workout_id=same_workout),
        ],
    )
    assert history.session_count == 1


# --------------------------------------------------------------- window bounds


@pytest.mark.parametrize(
    ("weeks", "expected"),
    [
        (1, date(2026, 7, 27)),   # this week alone — Wed 29th sits in the 27th's week
        (2, date(2026, 7, 20)),
        (12, date(2026, 5, 11)),
    ],
)
def test_window_starts_on_a_monday_and_includes_the_current_week(
    weeks: int, expected: date
) -> None:
    assert window_start(date(2026, 7, 29), weeks) == expected


# ------------------------------------------------------------ personal records


def test_records_pick_each_best_independently() -> None:
    """The heaviest bar and the best estimated max need not be the same session:
    a rep PR at a lighter load can beat a heavier low-rep set."""
    record = _build_record(
        uuid.uuid4(),
        "Barbell Bench Press",
        [
            _point(date(2026, 6, 1), Decimal("100"), 1),   # heaviest, 1RM 100.00
            _point(date(2026, 6, 8), Decimal("90"), 8),    # 1RM 114.00 — the better max
        ],
    )
    assert record.heaviest_weight_kg == Decimal("100")
    assert record.heaviest_weight_on == date(2026, 6, 1)
    assert record.best_estimated_one_rm == Decimal("114.00")
    assert record.best_estimated_one_rm_on == date(2026, 6, 8)


def test_an_equalled_record_keeps_the_day_it_was_first_set() -> None:
    record = _build_record(
        uuid.uuid4(),
        "Deadlift",
        [
            _point(date(2026, 6, 1), Decimal("140"), 3),
            _point(date(2026, 6, 15), Decimal("140"), 3),  # equalled, not beaten
        ],
    )
    assert record.heaviest_weight_on == date(2026, 6, 1)


def test_session_volume_sums_repeated_slots_in_one_workout() -> None:
    """Two bench slots in one session are one session's work. Comparing them
    separately would let a single-slot day beat a bigger split one."""
    split_day = uuid.uuid4()
    volumes = _session_volumes(
        [
            _point(date(2026, 6, 1), Decimal("60"), 10, sets=3, workout_id=split_day),
            _point(date(2026, 6, 1), Decimal("50"), 10, sets=3, workout_id=split_day),
        ]
    )
    assert volumes == [(date(2026, 6, 1), Decimal("3300.00"))]


def test_best_session_volume_prefers_the_bigger_split_session() -> None:
    split_day, single_day = uuid.uuid4(), uuid.uuid4()
    record = _build_record(
        uuid.uuid4(),
        "Barbell Bench Press",
        [
            _point(date(2026, 6, 1), Decimal("60"), 10, sets=3, workout_id=split_day),
            _point(date(2026, 6, 1), Decimal("50"), 10, sets=3, workout_id=split_day),
            _point(date(2026, 6, 8), Decimal("70"), 10, sets=3, workout_id=single_day),
        ],
    )
    # split day 1800 + 1500 = 3300 beats the single day's 2100
    assert record.best_session_volume_kg == Decimal("3300.00")
    assert record.best_session_volume_on == date(2026, 6, 1)


def test_bodyweight_movement_has_no_weight_records_but_still_has_a_card() -> None:
    """Pull-ups belong on the PR board — with reps and dates, not a blank row."""
    record = _build_record(
        uuid.uuid4(),
        "Pull-up",
        [
            _point(date(2026, 6, 1), None, 8),
            _point(date(2026, 6, 8), None, 10),
        ],
    )
    assert record.heaviest_weight_kg is None
    assert record.best_estimated_one_rm is None
    assert record.best_session_volume_kg is None
    assert record.session_count == 2
    assert record.last_performed_on == date(2026, 6, 8)


def test_records_ignore_unusable_estimates_but_keep_the_weight() -> None:
    """A 30-rep set has no meaningful 1RM, but the bar was still loaded — the
    weight record must not vanish because the estimate did."""
    record = _build_record(
        uuid.uuid4(),
        "Barbell Squat",
        [_point(date(2026, 6, 1), Decimal("80"), 30)],
    )
    assert record.heaviest_weight_kg == Decimal("80")
    assert record.best_estimated_one_rm is None
