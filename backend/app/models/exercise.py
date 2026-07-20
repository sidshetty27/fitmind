"""`exercises` — the shared catalog of movements."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Equipment, MuscleGroup, pg_enum

if TYPE_CHECKING:
    from app.models.workout_exercise import WorkoutExercise


class Exercise(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A movement definition — "Barbell Bench Press" — independent of any session.

    **This is the normalisation the phase is really about.** The obvious v1 is to
    put `exercise_name` as text on each logged row. It works until you ask the
    questions this product exists to answer:

      - "Is my bench pressing plateauing?" — needs every bench row to group
        together, but free text yields `Bench Press`, `bench press`, `BB Bench`,
        `Benchpress`, and they never group.
      - "How much chest volume this week?" — needs a muscle group per movement,
        which text does not carry.
      - Renaming a movement would mean an UPDATE across every historical row.

    Splitting the catalog out gives one row per movement with attributes attached
    to it, and logged sets reference it by id. That is what makes the AI features
    in Phase 6 possible at all. `docs/database.md` sketched the flat version as a
    pragmatic v1 and flagged this refinement — we are taking it now, while there
    is no production data to migrate.
    """

    __tablename__ = "exercises"

    # Uniqueness is the whole point — one movement, exactly one row — and it is
    # declared as a constraint in `__table_args__` (same rationale as `users`).
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Attributes that belong to the *movement*, not to any performance of it.
    # This is the textbook normalisation test: they depend only on the exercise,
    # so they live here and not on `workout_exercises`.
    primary_muscle_group: Mapped[MuscleGroup] = mapped_column(
        pg_enum(MuscleGroup, "muscle_group"), nullable=False, index=True
    )
    equipment: Mapped[Equipment] = mapped_column(
        pg_enum(Equipment, "equipment"), nullable=False
    )
    # Compound lifts drive strength progression; isolation work drives volume.
    # The AI coach weighs them differently.
    is_compound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    instructions: Mapped[str | None] = mapped_column(Text)

    workout_entries: Mapped[list["WorkoutExercise"]] = relationship(
        back_populates="exercise"
    )

    __table_args__ = (
        # Without this, "Barbell Bench Press" gets inserted twice and a user's
        # bench history silently splits across two ids — the exact failure this
        # table exists to prevent.
        UniqueConstraint("name", name="uq_exercises_name"),
    )

    def __repr__(self) -> str:
        return f"<Exercise id={self.id} name={self.name!r}>"
