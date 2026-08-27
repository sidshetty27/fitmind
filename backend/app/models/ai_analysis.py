"""`ai_analyses` — one stored run of the AI coach."""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class AiAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A coaching run: the findings that were computed, and what was said about them.

    **Why this is stored at all**, when the findings could be recomputed on demand:

      - *Quota.* Premium gates "unlimited AI analyses", which only means anything
        if analyses are countable. Counting rows in this table is the whole
        implementation; bolting a counter on later would start every existing user
        at zero with no history to justify it.
      - *Honesty over time.* A finding is true of a window, not forever. "Squat
        down 3.13%" recomputed next month silently becomes a different number, so
        a coaching note the user remembers reading would no longer match anything.
        Storing the run keeps the advice and the evidence that produced it
        together.
      - *Cost.* A model call is the expensive part of this feature. Re-rendering a
        page should not repeat it.

    `findings` holds the deterministic observations exactly as computed, and
    `narrative` holds the model's prose. They are separate columns because they
    have different trust levels: the findings are derived from the user's own rows
    and are reproducible, while the narrative is generated and may be absent —
    when there is no API key, when the user is over quota, or when the provider
    call failed. A row with findings and no narrative is a complete, useful
    analysis, not a broken one.
    """

    __tablename__ = "ai_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The window the findings describe. Stored rather than inferred from
    # created_at, because "the last 12 weeks" means something different depending
    # on when it was asked, and the answer has to stay readable later.
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    workout_count: Mapped[int] = mapped_column(nullable=False, default=0)

    # JSONB, not a child table: findings are read as a whole document, never
    # queried field-by-field, and their shape belongs to the analysis code rather
    # than the schema. A `findings` table would need a migration every time a
    # detector learned a new field.
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    narrative: Mapped[str | None] = mapped_column(Text)
    # Which model produced `narrative`, so a change in provider or version is
    # attributable after the fact. NULL whenever narrative is NULL.
    model: Mapped[str | None] = mapped_column(String(100))

    user: Mapped["User"] = relationship(back_populates="ai_analyses")

    __table_args__ = (
        CheckConstraint("window_end >= window_start", name="window_ordered"),
        CheckConstraint("workout_count >= 0", name="workout_count_non_negative"),
        # A narrative without a model is unattributable, and a model without a
        # narrative is a claim about nothing. They travel together.
        CheckConstraint(
            "(narrative IS NULL) = (model IS NULL)", name="narrative_model_together"
        ),
        # "This user's history, newest first" and "how many has this user run
        # recently" (the quota and per-user rate check). Both served by one
        # composite index.
        Index("ix_ai_analyses_user_id_created_at", "user_id", "created_at"),
        # The global rate limit counts runs by *everyone* in the last day, so it
        # has no user_id to lead with and cannot use the index above for a range
        # scan. Without this it degrades to reading the whole table — on the one
        # query that runs before every coach request, which is precisely the
        # request already about to be the most expensive thing the app does.
        Index("ix_ai_analyses_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AiAnalysis id={self.id} user_id={self.user_id} findings={len(self.findings)}>"
