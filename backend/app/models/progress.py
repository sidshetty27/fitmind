"""`progress_entries` — daily body/lifestyle metrics, separate from training."""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class ProgressEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One day's bodyweight / nutrition / sleep snapshot for one user.

    **Why this is its own table rather than columns on `users`.** `users.weight_kg`
    holds one number — today's. Progress is a time series, and answering "am I
    actually losing fat?" or "does poor sleep precede my plateaus?" requires the
    history. Overwriting a column destroys exactly the data the product is for.

    **Why it is separate from `workouts`.** These metrics are recorded on rest
    days too. Attaching them to workouts would make the series full of holes and
    would conflate two different things: what you did in the gym, and what your
    body is doing.

    Every measure is nullable and independent — logging weight without logging
    macros is the normal case, and demanding all-or-nothing would just stop people
    logging.
    """

    __tablename__ = "progress_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # DATE for the same reason as `workouts.performed_on`: this is a calendar day
    # in the user's timezone, not an instant.
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)

    bodyweight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    calories: Mapped[int | None] = mapped_column()
    protein_g: Mapped[int | None] = mapped_column()
    sleep_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="progress_entries")

    __table_args__ = (
        # One entry per user per day. This is the table's natural key, and
        # enforcing it in the database is what lets the API use a clean UPSERT
        # ("log today's weight" is idempotent) instead of a read-then-write race
        # that produces duplicate days under a double-tap.
        UniqueConstraint("user_id", "recorded_on", name="uq_progress_entries_user_id_recorded_on"),
        # No separate index for the "one user over a date range" chart query:
        # Postgres backs the UNIQUE constraint above with a btree on exactly
        # (user_id, recorded_on), which already serves that access pattern.
        # Adding one would cost write throughput and buy nothing.
        CheckConstraint("bodyweight_kg IS NULL OR bodyweight_kg > 0", name="bodyweight_positive"),
        CheckConstraint("calories IS NULL OR calories >= 0", name="calories_non_negative"),
        CheckConstraint("protein_g IS NULL OR protein_g >= 0", name="protein_non_negative"),
        CheckConstraint(
            "sleep_hours IS NULL OR (sleep_hours >= 0 AND sleep_hours <= 24)",
            name="sleep_hours_in_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProgressEntry id={self.id} user_id={self.user_id} on={self.recorded_on}>"
