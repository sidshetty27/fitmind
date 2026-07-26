"""`workout_templates` — a reusable session plan, not a session that happened."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workout_template_exercise import WorkoutTemplateExercise


class WorkoutTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named, reusable plan — "Push Day A" — that a user applies to log a session.

    **Why this is a separate table and not a flag on `workouts`.** Marking some
    workouts as `is_template=true` would be cheaper by one table, and wrong in
    three ways: a template has no `performed_on` (it never happened), it would
    pollute every history query, streak count, and volume aggregate with sessions
    the user did not train, and its weights are *targets* rather than facts. A
    plan and a record of the past are different things; conflating them means
    every read of the workout log has to remember to filter, and one forgotten
    `WHERE NOT is_template` silently corrupts a statistic.

    Applying a template is a copy, not a link: `POST /api/workouts` receives the
    template's exercises as its starting values, and the resulting workout is
    thereafter independent. Editing a template must not rewrite history that was
    already logged from it.
    """

    __tablename__ = "workout_templates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # Templates are personal, and go with the account. Same reasoning as
        # `workouts.user_id` — no orphaned rows after an account deletion.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Required, unlike `workouts.title`: a template is chosen from a list by name,
    # so an unnamed one is unusable. A workout is found by date and can be untitled.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="workout_templates")
    exercises: Mapped[list["WorkoutTemplateExercise"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutTemplateExercise.position",
    )

    __table_args__ = (
        # Scoped to the user, not global: two people may both have a "Push Day A",
        # and one user having two is a mistake they cannot tell apart in a picker.
        UniqueConstraint("user_id", "name", name="uq_workout_templates_user_id_name"),
        Index("ix_workout_templates_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<WorkoutTemplate id={self.id} user_id={self.user_id} name={self.name!r}>"
