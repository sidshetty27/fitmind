"""Pure training maths. No database, no ORM, no I/O — numbers in, numbers out.

Every function here is total: it either returns a value or `None`, and never
raises on data the database would accept. `None` consistently means *"not
applicable to this entry"*, never *"zero"* — the same convention
`workout_exercises.weight_kg` already uses for bodyweight movements. Collapsing
"no external load" into `0` would drag every volume and 1RM average toward zero
and quietly corrupt exactly the trends this layer exists to detect.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Above this rep count the Epley estimate stops tracking reality — it drifts high
# because it assumes a linear load/rep trade-off that endurance sets do not obey.
# We return None past it rather than a confident-looking wrong number: a missing
# 1RM leaves a gap in a chart, a bad one silently becomes a training decision.
MAX_RELIABLE_REPS = 12

_CENTS = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    """Round half-up to 2dp — matches `Numeric(6, 2)` storage, not banker's rounding."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def estimate_one_rm(weight_kg: Decimal | None, reps: int) -> Decimal | None:
    """Estimated one-rep max via Epley: `w x (1 + reps/30)`.

    Returns `None` when the estimate would be meaningless rather than guessing:

      - `weight_kg is None` — a bodyweight movement has no external load to
        extrapolate from. Dips and pull-ups still count as training; they just
        do not have a 1RM in this sense.
      - `weight_kg == 0` — same situation recorded differently.
      - `reps` outside `1..MAX_RELIABLE_REPS`.

    A single rep is returned unchanged. Epley would scale it by 1.033, which is
    wrong by definition: a 1-rep set *is* the measured max, not an estimate of it.
    """
    if weight_kg is None or weight_kg <= 0:
        return None
    if reps < 1 or reps > MAX_RELIABLE_REPS:
        return None
    if reps == 1:
        return _round2(weight_kg)
    return _round2(weight_kg * (Decimal(1) + Decimal(reps) / Decimal(30)))


def entry_volume(sets: int, reps: int, weight_kg: Decimal | None) -> Decimal | None:
    """Volume load for one logged movement: `sets x reps x weight`.

    `None` for bodyweight work, for the reason in the module docstring. Callers
    summing a mixed session must skip the `None`s and report total reps
    alongside — see `total_reps`, which stays meaningful when load does not.
    """
    if weight_kg is None or weight_kg <= 0:
        return None
    return _round2(Decimal(sets) * Decimal(reps) * weight_kg)


def total_reps(sets: int, reps: int) -> int:
    """Reps performed for one movement. Defined for loaded and bodyweight alike."""
    return sets * reps


def best_estimated_one_rm(
    entries: list[tuple[Decimal | None, int]],
) -> Decimal | None:
    """Highest estimated 1RM across `(weight_kg, reps)` pairs, or `None` if no pair
    yields one.

    Takes the best rather than the last or the mean: a session's top set is the
    signal, while warm-up and back-off sets would drag an average down and make
    a productive day look like a regression.
    """
    estimates = [
        estimate for weight, reps in entries if (estimate := estimate_one_rm(weight, reps))
    ]
    return max(estimates) if estimates else None


def percent_change(earlier: Decimal | None, later: Decimal | None) -> Decimal | None:
    """Percent change from `earlier` to `later`, 2dp. `None` if either is missing
    or `earlier` is zero.

    Signed on purpose: a negative result is a real finding (deload, injury,
    regression), not an error to clamp away.
    """
    if earlier is None or later is None or earlier == 0:
        return None
    return _round2((later - earlier) / earlier * Decimal(100))


__all__ = [
    "MAX_RELIABLE_REPS",
    "best_estimated_one_rm",
    "entry_volume",
    "estimate_one_rm",
    "percent_change",
    "total_reps",
]
