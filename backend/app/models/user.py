"""`users` — the internal identity row that every other table hangs off."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExperienceLevel, Goal, pg_enum

if TYPE_CHECKING:  # avoid circular imports at runtime; relationships use strings
    from app.models.progress import ProgressEntry
    from app.models.workout import Workout


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A FitMind account, mirrored from Clerk.

    **Why we store users at all when Clerk already has them.** Clerk owns
    authentication; it does not own our data model. Foreign keys need a local
    primary key, and `workouts.user_id -> clerk.user_id` would mean every join
    depends on an external service's identifier format. So Clerk stays the source
    of truth for *identity* (who you are, your password, your email verification)
    and this table is the source of truth for *the application's* user — with
    `clerk_id` as the single join point between the two systems.

    Consequently this table deliberately does NOT store credentials, password
    hashes, session state, or verification status. Duplicating those would create
    two systems that can disagree about whether you are logged in.
    """

    __tablename__ = "users"

    # The join point to Clerk (Clerk's `user_...` identifier).
    # String, not UUID: Clerk's ids are prefixed opaque strings, and pinning our
    # column to their current format would be a bet we do not need to take.
    # Uniqueness is an explicit constraint in `__table_args__`, not `unique=True`
    # here — see the note there.
    clerk_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Cached from Clerk so we can render and email without an API call per request.
    # Clerk remains authoritative; a Phase 4 webhook keeps these fresh.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))

    # --- Profile (all nullable: onboarding is progressive, not a gate) ---
    # Numeric, never float: 72.4 kg has no exact binary representation, and
    # accumulated float drift in a strength-progression chart is indefensible
    # when the fix is free. Numeric(5,2) covers 0.00–999.99.
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Current weight, cached for convenience. The *history* lives in
    # `progress_entries` — this is the denormalised "latest" value, and
    # `progress_entries` is the system of record.
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    goal: Mapped[Goal | None] = mapped_column(pg_enum(Goal, "goal"))
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        pg_enum(ExperienceLevel, "experience_level")
    )

    # --- Relationships ---
    # `cascade="all, delete-orphan"` is the ORM-side rule; the FK columns also
    # declare `ondelete="CASCADE"`. Both are needed: the ORM rule handles objects
    # already loaded in the session, the DB rule handles everything else
    # (bulk deletes, psql, another service). Only one of them is enforcement.
    workouts: Mapped[list["Workout"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    progress_entries: Mapped[list["ProgressEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # Declared as constraints rather than `unique=True` on the columns, which
        # SQLAlchemy renders as a unique *index* instead. Both enforce uniqueness,
        # but they are different schema objects, so mixing the two styles between
        # models and migrations makes `alembic revision --autogenerate` report
        # phantom drift forever. One style, stated explicitly.
        #
        # No extra index on clerk_id despite it being the hottest lookup in the
        # app (every authenticated request resolves Clerk's `sub` through it):
        # Postgres backs a UNIQUE constraint with a btree on that column, and
        # that index already serves the lookup.
        UniqueConstraint("clerk_id", name="uq_users_clerk_id"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("height_cm IS NULL OR height_cm > 0", name="height_positive"),
        CheckConstraint("weight_kg IS NULL OR weight_kg > 0", name="weight_positive"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} clerk_id={self.clerk_id!r}>"
