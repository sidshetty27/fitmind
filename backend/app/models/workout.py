"""`workouts` — one training session."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workout_exercise import WorkoutExercise


class Workout(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single session on a single day. Owns its exercise entries."""

    __tablename__ = "workouts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # ondelete CASCADE: deleting an account must not leave orphaned training
        # data behind — both for correctness and for GDPR-style deletion requests.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # `performed_on`, not `date`: `date` is a reserved word in SQL, so every
    # hand-written query would need `"date"` quoted, and it reads ambiguously
    # next to `created_at`. This is the day the training happened; `created_at`
    # is when the row was written. They differ whenever someone logs yesterday's
    # session, and conflating them corrupts every streak and trend calculation.
    #
    # DATE, not TIMESTAMPTZ: a workout belongs to a calendar day in the user's own
    # timezone. Storing an instant would make "did I train today?" depend on the
    # server's timezone — the classic bug where a 9pm PST workout counts as
    # tomorrow. The client resolves the local day; we store exactly that.
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)

    duration_min: Mapped[int | None] = mapped_column()
    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="workouts")
    exercises: Mapped[list["WorkoutExercise"]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
        passive_deletes=True,
        # Deterministic ordering so the API never returns a user's sets shuffled.
        order_by="WorkoutExercise.position",
    )

    __table_args__ = (
        # The dashboard's core query is "this user's workouts, newest first".
        # A composite index on (user_id, performed_on) serves both the filter and
        # the sort from one structure — an index on user_id alone would still
        # force a sort. Column order matters: user_id is the equality predicate
        # and must come first. No DESC needed: Postgres scans a btree in either
        # direction, so this index satisfies ASC and DESC ordering alike.
        Index("ix_workouts_user_id_performed_on", "user_id", "performed_on"),
        CheckConstraint(
            "duration_min IS NULL OR duration_min > 0", name="duration_positive"
        ),
    )

    def __repr__(self) -> str:
        return f"<Workout id={self.id} user_id={self.user_id} on={self.performed_on}>"
