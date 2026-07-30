"""Findings tests — the observations the AI coach is handed as fact.

These run unconditionally, with no database. That is the point: every number the
coach states about a user's training originates here, so this is the suite that
has to be right. A wrong percentage delivered in a confident coaching voice is
the worst failure this feature has.

The emphasis is deliberately on what each detector *refuses* to say. Firing on
thin evidence is how a coach becomes noise, and noise gets switched off.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.analysis import findings, metrics
from app.analysis.findings import FindingKind
from app.models.enums import MuscleGroup
from app.schemas.analysis import ExerciseHistory, ExerciseSessionPoint, TrainingSummary

TODAY = date(2026, 7, 29)


def _point(
    performed_on: date,
    weight: Decimal | None,
    reps: int,
    *,
    sets: int = 3,
    rpe: Decimal | None = None,
) -> ExerciseSessionPoint:
    return ExerciseSessionPoint(
        workout_id=uuid.uuid4(),
        performed_on=performed_on,
        sets=sets,
        reps=reps,
        weight_kg=weight,
        rpe=rpe,
        volume_kg=metrics.entry_volume(sets, reps, weight),
        estimated_one_rm=metrics.estimate_one_rm(weight, reps),
        total_reps=metrics.total_reps(sets, reps),
    )


def _history(
    name: str,
    points: list[ExerciseSessionPoint],
    *,
    group: MuscleGroup = MuscleGroup.CHEST,
    sessions: int | None = None,
    change_pct: Decimal | None = None,
    best: Decimal | None = None,
) -> ExerciseHistory:
    return ExerciseHistory(
        exercise_id=uuid.uuid4(),
        exercise_name=name,
        primary_muscle_group=group,
        points=points,
        session_count=sessions if sessions is not None else len(points),
        best_estimated_one_rm=best,
        one_rm_change_pct=change_pct,
    )


def _summary(*histories: ExerciseHistory) -> TrainingSummary:
    return TrainingSummary(
        window_start=date(2026, 5, 11),
        window_end=TODAY,
        workout_count=sum(h.session_count for h in histories),
        weekly_volume=[],
        exercises=list(histories),
    )


def _kinds(results: list[findings.Finding]) -> list[FindingKind]:
    return [f.kind for f in results]


# ---------------------------------------------------------------------- plateau


def test_plateau_reported_when_a_well_trained_lift_stops_moving() -> None:
    summary = _summary(
        _history("Barbell Bench Press", [], sessions=8, change_pct=Decimal("0.5"))
    )
    [found] = findings.detect_plateaus(summary)
    assert found.kind is FindingKind.PLATEAU
    assert "stalled" in found.statement
    assert "0.5%" in found.statement


def test_a_decline_is_named_as_one_rather_than_softened() -> None:
    summary = _summary(
        _history("Barbell Back Squat", [], sessions=7, change_pct=Decimal("-3.13"))
    )
    [found] = findings.detect_plateaus(summary)
    assert "gone backwards" in found.statement
    # The sign is carried by the wording; the number itself reads as a magnitude.
    assert "3.13%" in found.statement
    assert found.detail["change_pct"] == "-3.13"


def test_progress_is_not_a_plateau() -> None:
    summary = _summary(
        _history("Barbell Deadlift", [], sessions=10, change_pct=Decimal("27.78"))
    )
    assert findings.detect_plateaus(summary) == []


def test_too_few_sessions_stays_quiet() -> None:
    """Three points can drift for reasons that are not adaptation. Calling that a
    plateau would be a guess wearing a number."""
    summary = _summary(
        _history(
            "Barbell Row",
            [],
            sessions=findings.MIN_SESSIONS_FOR_TREND - 1,
            change_pct=Decimal("0"),
        )
    )
    assert findings.detect_plateaus(summary) == []


def test_a_movement_with_no_trend_at_all_stays_quiet() -> None:
    """Bodyweight work has no estimable max, so it can never be a plateau."""
    summary = _summary(_history("Pull-Up", [], sessions=10, change_pct=None))
    assert findings.detect_plateaus(summary) == []


# ------------------------------------------------------------------ volume drop


def test_volume_drop_reported_with_both_totals() -> None:
    # Prior block: 3x10x60 = 1800 each. Recent block: 3x10x30 = 900 each.
    points = [
        _point(date(2026, 7, 1), Decimal("60"), 10),
        _point(date(2026, 7, 6), Decimal("60"), 10),
        _point(date(2026, 7, 20), Decimal("30"), 10),
        _point(date(2026, 7, 27), Decimal("30"), 10),
    ]
    summary = _summary(_history("Barbell Back Squat", points))
    [found] = findings.detect_volume_drops(summary, TODAY)
    assert found.kind is FindingKind.VOLUME_DROP
    assert found.detail["change_pct"] == "-50.00"
    assert "3,600 kg" in found.statement and "1,800 kg" in found.statement


def test_a_small_dip_is_not_worth_saying() -> None:
    points = [
        _point(date(2026, 7, 6), Decimal("60"), 10),
        _point(date(2026, 7, 27), Decimal("57.5"), 10),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    assert findings.detect_volume_drops(summary, TODAY) == []


def test_a_new_movement_is_not_a_drop() -> None:
    """Nothing in the earlier block means new, not down 100%."""
    points = [_point(date(2026, 7, 27), Decimal("60"), 10)]
    summary = _summary(_history("Leg Press", points))
    assert findings.detect_volume_drops(summary, TODAY) == []


def test_a_movement_that_stopped_entirely_is_left_to_the_staleness_finding() -> None:
    """Reporting it here as "down 100%" would double up on a finding that says
    something more useful."""
    points = [_point(date(2026, 7, 1), Decimal("60"), 10)]
    summary = _summary(_history("Barbell Row", points, group=MuscleGroup.BACK))
    assert findings.detect_volume_drops(summary, TODAY) == []


def test_bodyweight_work_never_produces_a_volume_drop() -> None:
    points = [
        _point(date(2026, 7, 1), None, 10),
        _point(date(2026, 7, 27), None, 6),
    ]
    summary = _summary(_history("Pull-Up", points, group=MuscleGroup.BACK))
    assert findings.detect_volume_drops(summary, TODAY) == []


# ------------------------------------------------------------------- staleness


def test_stale_group_reported_with_the_day_count() -> None:
    summary = _summary(
        _history(
            "Barbell Romanian Deadlift",
            [_point(date(2026, 7, 10), Decimal("70"), 8)],
            group=MuscleGroup.HAMSTRINGS,
        )
    )
    [found] = findings.detect_stale_muscle_groups(summary, TODAY)
    assert found.subject == "hamstrings"
    assert "19 days" in found.statement
    assert found.detail["days_since"] == 19


def test_recently_trained_groups_are_not_mentioned() -> None:
    summary = _summary(
        _history(
            "Barbell Bench Press",
            [_point(date(2026, 7, 27), Decimal("60"), 8)],
            group=MuscleGroup.CHEST,
        )
    )
    assert findings.detect_stale_muscle_groups(summary, TODAY) == []


def test_a_group_is_only_as_stale_as_its_most_recent_movement() -> None:
    """Two chest movements, one long abandoned — the group is not stale."""
    summary = _summary(
        _history(
            "Cable Chest Fly",
            [_point(date(2026, 5, 12), Decimal("20"), 12)],
            group=MuscleGroup.CHEST,
        ),
        _history(
            "Barbell Bench Press",
            [_point(date(2026, 7, 28), Decimal("60"), 8)],
            group=MuscleGroup.CHEST,
        ),
    )
    assert findings.detect_stale_muscle_groups(summary, TODAY) == []


def test_groups_never_trained_are_not_invented() -> None:
    """A coach that nags about movements a user deliberately excludes gets muted."""
    summary = _summary(
        _history(
            "Barbell Bench Press",
            [_point(date(2026, 7, 28), Decimal("60"), 8)],
            group=MuscleGroup.CHEST,
        )
    )
    subjects = {f.subject for f in findings.detect_stale_muscle_groups(summary, TODAY)}
    assert "calves" not in subjects


def test_stalest_group_is_reported_first() -> None:
    summary = _summary(
        _history(
            "Calf Raise",
            [_point(date(2026, 7, 15), Decimal("40"), 12)],
            group=MuscleGroup.CALVES,
        ),
        _history(
            "Leg Curl",
            [_point(date(2026, 6, 1), Decimal("30"), 12)],
            group=MuscleGroup.HAMSTRINGS,
        ),
    )
    results = findings.detect_stale_muscle_groups(summary, TODAY)
    assert [f.subject for f in results] == ["hamstrings", "calves"]


# ------------------------------------------------------------ ready to progress


def test_comfortable_reps_at_a_held_load_suggest_a_step_up() -> None:
    points = [
        _point(date(2026, 7, 20), Decimal("60"), 8, rpe=Decimal("7")),
        _point(date(2026, 7, 27), Decimal("60"), 8, rpe=Decimal("7")),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    [found] = findings.detect_ready_to_progress(summary)
    assert found.kind is FindingKind.READY_TO_PROGRESS
    assert found.detail["suggested_weight_kg"] == "62.5"


def test_a_hard_grind_is_not_an_invitation_to_add_weight() -> None:
    points = [
        _point(date(2026, 7, 20), Decimal("60"), 8, rpe=Decimal("9")),
        _point(date(2026, 7, 27), Decimal("60"), 8, rpe=Decimal("9.5")),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    assert findings.detect_ready_to_progress(summary) == []


def test_a_load_that_is_already_climbing_needs_no_suggestion() -> None:
    points = [
        _point(date(2026, 7, 20), Decimal("60"), 8, rpe=Decimal("7")),
        _point(date(2026, 7, 27), Decimal("62.5"), 8, rpe=Decimal("7")),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    assert findings.detect_ready_to_progress(summary) == []


def test_without_rpe_there_is_no_evidence_of_comfort() -> None:
    """A repeated load is just as consistent with a hard grind as an easy one."""
    points = [
        _point(date(2026, 7, 20), Decimal("60"), 8),
        _point(date(2026, 7, 27), Decimal("60"), 8),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    assert findings.detect_ready_to_progress(summary) == []


@pytest.mark.parametrize("rpe", [Decimal("7.5"), Decimal("7.4")])
def test_the_comfortable_boundary_itself_counts_as_comfortable(rpe: Decimal) -> None:
    points = [
        _point(date(2026, 7, 20), Decimal("60"), 8, rpe=rpe),
        _point(date(2026, 7, 27), Decimal("60"), 8, rpe=rpe),
    ]
    summary = _summary(_history("Barbell Bench Press", points))
    assert len(findings.detect_ready_to_progress(summary)) == 1


# ------------------------------------------------------------------- the whole set


def test_analyse_orders_problems_before_opportunities() -> None:
    """Stale groups first, then drops, then plateaus, then what is going well —
    the order the coach is expected to respect when it prioritises."""
    stale = _history(
        "Leg Curl",
        [_point(date(2026, 6, 1), Decimal("30"), 12)],
        group=MuscleGroup.HAMSTRINGS,
    )
    dropped = _history(
        "Barbell Back Squat",
        [
            _point(date(2026, 7, 1), Decimal("60"), 10),
            _point(date(2026, 7, 6), Decimal("60"), 10),
            _point(date(2026, 7, 20), Decimal("30"), 10),
            _point(date(2026, 7, 27), Decimal("30"), 10),
        ],
        group=MuscleGroup.QUADS,
    )
    ready = _history(
        "Barbell Bench Press",
        [
            _point(date(2026, 7, 20), Decimal("60"), 8, rpe=Decimal("7")),
            _point(date(2026, 7, 27), Decimal("60"), 8, rpe=Decimal("7")),
        ],
    )
    stalled = _history("Barbell Row", [], sessions=8, change_pct=Decimal("1"))

    kinds = _kinds(findings.analyse(_summary(stale, dropped, ready, stalled), TODAY))
    assert kinds.index(FindingKind.STALE_MUSCLE_GROUP) < kinds.index(
        FindingKind.VOLUME_DROP
    )
    assert kinds.index(FindingKind.VOLUME_DROP) < kinds.index(FindingKind.PLATEAU)
    assert kinds.index(FindingKind.PLATEAU) < kinds.index(
        FindingKind.READY_TO_PROGRESS
    )


def test_an_empty_history_produces_nothing_rather_than_failing() -> None:
    assert findings.analyse(_summary(), TODAY) == []


def test_every_finding_serialises_for_storage() -> None:
    summary = _summary(
        _history("Barbell Back Squat", [], sessions=7, change_pct=Decimal("-3.13"))
    )
    [found] = findings.analyse(summary, TODAY)
    payload = found.as_dict()
    assert payload["kind"] == "plateau"
    assert isinstance(payload["statement"], str)
    # Decimals are stringified, not floated — the same reason the wire format does it.
    assert payload["detail"]["change_pct"] == "-3.13"
