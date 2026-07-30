"""Training findings — the observations, computed rather than generated.

This is the layer that makes the coach trustworthy. Every number a user is shown
("squat volume is down 18%", "10 days since you trained hamstrings") is derived
here, from their logged rows, by pure functions with unit tests. The language
model that runs downstream is handed these findings as *facts*; its job is to
prioritise them and write the coaching voice, never to do the arithmetic.

The split matters. A model asked to compute a percentage from a table of sets
will occasionally get it wrong, and a training app that confidently reports the
wrong number is worse than one that reports nothing. It also means the whole
feature degrades honestly: with no API key, or a user over their quota, the
findings still stand on their own as a list of observations.

Every detector is deliberately conservative — it stays quiet unless it has enough
data to be sure. A coach that fires on one session is noise, and users switch
noise off.
"""

from __future__ import annotations

import enum
from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.analysis import metrics
from app.models.enums import MuscleGroup
from app.schemas.analysis import ExerciseHistory, TrainingSummary

# ------------------------------------------------------------------ thresholds
#
# Named, not inlined, because these are training judgements rather than facts —
# the number to argue about should be visible in one place.

#: Sessions of a movement needed before its trend means anything.
MIN_SESSIONS_FOR_TREND = 4
#: Best-estimate gain below this over the window reads as "stalled", not "progress".
PLATEAU_GAIN_PCT = Decimal("2")
#: Volume drop against the previous block worth mentioning.
VOLUME_DROP_PCT = Decimal("15")
#: Whole weeks per block when comparing recent work against what came before.
BLOCK_WEEKS = 3
#: Days without touching a muscle group before it is called stale.
STALE_DAYS = 10
#: An RPE at or below this, held across sessions at one load, means there is room.
COMFORTABLE_RPE = Decimal("7.5")
#: Sessions at the same load needed before suggesting more of it.
MIN_SESSIONS_AT_LOAD = 2


class FindingKind(str, enum.Enum):
    PLATEAU = "plateau"
    VOLUME_DROP = "volume_drop"
    STALE_MUSCLE_GROUP = "stale_muscle_group"
    READY_TO_PROGRESS = "ready_to_progress"


class Finding:
    """One observation, with the numbers that produced it.

    `statement` is already true and already specific — it is what gets shown when
    there is no model available, and what the model is told it may rephrase but
    must not contradict.
    """

    __slots__ = ("kind", "subject", "statement", "detail")

    def __init__(
        self,
        kind: FindingKind,
        subject: str,
        statement: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.kind = kind
        self.subject = subject
        self.statement = statement
        self.detail = detail or {}

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "subject": self.subject,
            "statement": self.statement,
            "detail": self.detail,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Finding {self.kind.value} {self.subject!r}>"


def _plural_days(days: int) -> str:
    return "1 day" if days == 1 else f"{days} days"


# ---------------------------------------------------------------------- plateau


def detect_plateaus(summary: TrainingSummary) -> list[Finding]:
    """Movements trained often enough to expect progress, that are not progressing.

    Requires `MIN_SESSIONS_FOR_TREND` sessions: two or three data points can drift
    for reasons that have nothing to do with adaptation (a bad night's sleep, a
    different bar), and calling that a plateau would be a guess wearing a number.

    A *negative* change is reported too, and named as a decline rather than
    softened — that is the finding most worth acting on.
    """
    findings: list[Finding] = []
    for exercise in summary.exercises:
        change = exercise.one_rm_change_pct
        if change is None or exercise.session_count < MIN_SESSIONS_FOR_TREND:
            continue
        if change > PLATEAU_GAIN_PCT:
            continue

        if change < 0:
            statement = (
                f"{exercise.exercise_name} has gone backwards: your estimated max is "
                f"down {abs(change)}% across {exercise.session_count} sessions."
            )
        else:
            statement = (
                f"{exercise.exercise_name} has stalled — your estimated max moved "
                f"{change}% across {exercise.session_count} sessions."
            )
        findings.append(
            Finding(
                FindingKind.PLATEAU,
                exercise.exercise_name,
                statement,
                {
                    "change_pct": str(change),
                    "sessions": exercise.session_count,
                    "best_estimated_one_rm": str(exercise.best_estimated_one_rm)
                    if exercise.best_estimated_one_rm is not None
                    else None,
                },
            )
        )
    return findings


# ------------------------------------------------------------------ volume drop


def detect_volume_drops(summary: TrainingSummary, today: date) -> list[Finding]:
    """Per-movement load compared against the block before it.

    Blocks rather than a single week: one light week is a deload or a busy week,
    and flagging it would train the user to ignore the coach. Two blocks of
    `BLOCK_WEEKS` is a change in behaviour.

    Both blocks must contain work. A movement absent from the earlier block is not
    "down 100%", it is new — and a movement absent from the recent one is covered
    by the staleness finding instead, which says something more useful.
    """
    findings: list[Finding] = []
    recent_start = today.toordinal() - BLOCK_WEEKS * 7
    prior_start = recent_start - BLOCK_WEEKS * 7

    for exercise in summary.exercises:
        recent = Decimal("0")
        prior = Decimal("0")
        for point in exercise.points:
            if point.volume_kg is None:
                continue
            day = point.performed_on.toordinal()
            if day > recent_start:
                recent += point.volume_kg
            elif day > prior_start:
                prior += point.volume_kg

        if prior <= 0 or recent <= 0:
            continue
        change = metrics.percent_change(prior, recent)
        if change is None or change > -VOLUME_DROP_PCT:
            continue

        findings.append(
            Finding(
                FindingKind.VOLUME_DROP,
                exercise.exercise_name,
                f"Your {exercise.exercise_name} volume is down {abs(change)}% over the "
                f"past {BLOCK_WEEKS} weeks ({int(prior):,} kg to {int(recent):,} kg).",
                {
                    "change_pct": str(change),
                    "prior_volume_kg": str(prior),
                    "recent_volume_kg": str(recent),
                    "block_weeks": BLOCK_WEEKS,
                },
            )
        )
    return findings


# ------------------------------------------------------------------- staleness


def detect_stale_muscle_groups(
    summary: TrainingSummary, today: date
) -> list[Finding]:
    """Muscle groups the user trains, but has not trained lately.

    Scoped to groups already present in the window on purpose. Telling someone
    they have "never trained calves" is not a finding about their training, it is
    a complaint about their programme — and a coach that nags about movements a
    user has deliberately excluded gets muted.
    """
    last_trained: dict[MuscleGroup, date] = {}
    for exercise in summary.exercises:
        if not exercise.points:
            continue
        latest = max(point.performed_on for point in exercise.points)
        group = exercise.primary_muscle_group
        if group not in last_trained or latest > last_trained[group]:
            last_trained[group] = latest

    findings: list[Finding] = []
    for group, seen in sorted(last_trained.items(), key=lambda kv: kv[1]):
        days = (today - seen).days
        if days < STALE_DAYS:
            continue
        findings.append(
            Finding(
                FindingKind.STALE_MUSCLE_GROUP,
                group.value,
                f"You haven't trained {group.value.replace('_', ' ')} in "
                f"{_plural_days(days)}.",
                {"days_since": days, "last_trained_on": seen.isoformat()},
            )
        )
    return findings


# ------------------------------------------------------------ ready to progress


def detect_ready_to_progress(summary: TrainingSummary) -> list[Finding]:
    """Movements sitting at one load, and sitting there comfortably.

    Needs RPE: without it there is no evidence the load is easy, only that it
    repeated — which is just as consistent with a hard grind. Movements logged
    without RPE are skipped rather than guessed at.
    """
    findings: list[Finding] = []
    for exercise in summary.exercises:
        loaded = [p for p in exercise.points if p.weight_kg is not None and p.rpe is not None]
        if len(loaded) < MIN_SESSIONS_AT_LOAD:
            continue

        recent = loaded[-MIN_SESSIONS_AT_LOAD:]
        weight = recent[0].weight_kg
        if any(point.weight_kg != weight for point in recent):
            continue
        if any(point.rpe > COMFORTABLE_RPE for point in recent):  # type: ignore[operator]
            continue

        suggestion = _next_load(weight)  # type: ignore[arg-type]
        findings.append(
            Finding(
                FindingKind.READY_TO_PROGRESS,
                exercise.exercise_name,
                f"{exercise.exercise_name} has stayed at {weight} kg for "
                f"{len(recent)} sessions at RPE {max(p.rpe for p in recent)} or below — "  # type: ignore[type-var]
                f"there is room to try {suggestion} kg.",
                {
                    "current_weight_kg": str(weight),
                    "suggested_weight_kg": str(suggestion),
                    "sessions_at_load": len(recent),
                },
            )
        )
    return findings


def _next_load(weight: Decimal) -> Decimal:
    """The next sensible jump: 2.5 kg, the smallest increment most gyms can make.

    Proportional stepping would suggest a 0.6 kg increase on a light accessory and
    5 kg on a heavy squat; the first is unloadable and the second is a big jump.
    A fixed plate-sized step is what a lifter can actually act on.
    """
    return weight + Decimal("2.5")


# ------------------------------------------------------------------ the whole set


def analyse(summary: TrainingSummary, today: date) -> list[Finding]:
    """Every finding for one user's window, most actionable first.

    The order is the priority the coach should respect: things going wrong before
    things going well, and within that, whole muscle groups before single lifts —
    a neglected muscle group is a bigger programme problem than one stalled lift.

    `summary` must come from `crud.analysis.coaching_summary`, not
    `training_summary`. The latter caps movements by session count, which silently
    removes the neglected ones these detectors are looking for.
    """
    return [
        *detect_stale_muscle_groups(summary, today),
        *detect_volume_drops(summary, today),
        *detect_plateaus(summary),
        *detect_ready_to_progress(summary),
    ]


__all__ = [
    "BLOCK_WEEKS",
    "COMFORTABLE_RPE",
    "Finding",
    "FindingKind",
    "MIN_SESSIONS_AT_LOAD",
    "MIN_SESSIONS_FOR_TREND",
    "PLATEAU_GAIN_PCT",
    "STALE_DAYS",
    "VOLUME_DROP_PCT",
    "analyse",
    "detect_plateaus",
    "detect_ready_to_progress",
    "detect_stale_muscle_groups",
    "detect_volume_drops",
]
