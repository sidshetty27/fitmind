"""`workout_template_exercises` — one planned movement inside a template."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.workout_template import WorkoutTemplate


class WorkoutTemplateExercise(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A prescribed movement: what to do, not what was done.

    Deliberately mirrors `WorkoutExercise` column for column — same names, same
    types, same constraints. Applying a template is then a field-for-field copy
    with no translation layer, and the two stay comparable ("did I hit the plan?")
    without a mapping table that would drift the moment either side gains a column.

    `sets` and `reps` are required for the same reason they are on
    `WorkoutExercise`: applying a template produces a workout, and a workout
    demands both. Allowing a template to omit them would let a user save a plan
    that cannot actually be applied — a failure discovered at use time rather than
    at save time. `weight_kg` and `rpe` stay nullable because a plan legitimately
    says "3x8, work up to something hard".
    """

    __tablename__ = "workout_template_exercises"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT, matching `workout_exercises`: the catalog is shared reference
        # data and deleting a movement must not quietly gut everyone's templates.
        ForeignKey("exercises.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    position: Mapped[int] = mapped_column(nullable=False)

    sets: Mapped[int] = mapped_column(nullable=False)
    reps: Mapped[int] = mapped_column(nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    notes: Mapped[str | None] = mapped_column(Text)

    template: Mapped["WorkoutTemplate"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship()

    # Constraint names follow the same shape the sibling table uses, so both are
    # exactly what `NAMING_CONVENTION` would generate. Anything else shows up as
    # permanent phantom drift in every future `alembic revision --autogenerate`.
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "position",
            name="uq_workout_template_exercises_template_id_position",
        ),
        Index("ix_workout_template_exercises_template_id", "template_id"),
        CheckConstraint("sets > 0", name="sets_positive"),
        CheckConstraint("reps > 0", name="reps_positive"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg >= 0", name="weight_non_negative"
        ),
        CheckConstraint(
            "rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WorkoutTemplateExercise id={self.id} "
            f"template_id={self.template_id} pos={self.position}>"
        )
