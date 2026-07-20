"""`workout_exercises` — one movement as actually performed in one session."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.workout import Workout


class WorkoutExercise(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Join between `workouts` and `exercises`, carrying the performance data.

    This is an **association object**, not a bare many-to-many join table. A
    plain join table would only hold the two foreign keys; this one holds the
    facts that exist solely because *this* movement was done in *this* session —
    sets, reps, weight, RPE. Those attributes belong to the pairing itself, which
    is exactly when an association object is the right shape.

    **Known simplification:** one row aggregates all sets of a movement
    (`3 x 8 @ 60kg`). It cannot express a top-set/back-off scheme
    (`1x5 @ 100, 2x8 @ 80`) or a dropset. The fully normalised form is a further
    `exercise_sets` table, one row per set, with this row as its parent. We are
    starting here because the aggregate covers the overwhelming majority of
    logging, and because the split is additive later: `exercise_sets` gets a FK to
    this table and these columns become derived. Recorded so it is a decision, not
    an oversight.
    """

    __tablename__ = "workout_exercises"

    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE: these rows are parts of the workout, meaningless without it.
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT, deliberately NOT cascade: the catalog is shared reference
        # data. Deleting "Barbell Squat" must not silently erase two years of
        # squat history from every user's log. The delete is refused instead, and
        # retiring a movement becomes an explicit archival decision.
        ForeignKey("exercises.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Display/execution order within the session. Explicit, because insertion
    # order is not a thing a relational table preserves — without this column,
    # "what order did I do these in?" is unanswerable.
    position: Mapped[int] = mapped_column(nullable=False)

    sets: Mapped[int] = mapped_column(nullable=False)
    reps: Mapped[int] = mapped_column(nullable=False)
    # Nullable: bodyweight movements genuinely have no load. 0 would be a lie
    # that skews every volume average; NULL means "not applicable", which is what
    # aggregate functions already know how to skip.
    # Numeric(6,2) — exact decimals, up to 9999.99 (plenty for kg or lb).
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    # Rate of Perceived Exertion, 1–10 in half-point steps. The key input for
    # detecting "same weight, higher effort" — i.e. an incoming plateau.
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    notes: Mapped[str | None] = mapped_column(Text)

    workout: Mapped["Workout"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship(back_populates="workout_entries")

    __table_args__ = (
        # Two rows cannot claim the same slot in a session. Note what is NOT
        # constrained: (workout_id, exercise_id) is intentionally free to repeat,
        # because doing bench press twice in one session is legitimate training,
        # not a data error. This is why the natural key is position, not exercise.
        UniqueConstraint("workout_id", "position", name="uq_workout_exercises_workout_id_position"),
        # Covers "load this workout's exercises" and cascade deletes.
        Index("ix_workout_exercises_workout_id", "workout_id"),
        # Constraints, not application validation: the API is not the only thing
        # that will ever write here (migrations, backfills, psql, a future job).
        # Invariants that must always hold belong where they cannot be bypassed.
        CheckConstraint("sets > 0", name="sets_positive"),
        CheckConstraint("reps > 0", name="reps_positive"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("weight_kg IS NULL OR weight_kg >= 0", name="weight_non_negative"),
        CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"),
    )

    def __repr__(self) -> str:
        return f"<WorkoutExercise id={self.id} workout_id={self.workout_id} pos={self.position}>"
