"""`subscriptions` — what Stripe knows about a user's plan, mirrored locally."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One user's billing state, as last reported by Stripe.

    **Why mirror this at all when Stripe is authoritative.** Entitlement is
    checked on requests that have nothing to do with billing — every coach run
    asks "is this user premium?". Answering that by calling Stripe would put a
    third-party HTTP round trip, and a third-party outage, on an ordinary request
    path. Same reasoning as `config.py` verifying Clerk tokens against cached
    JWKS instead of calling Clerk per request: the external system owns the
    truth, we keep a local copy fast enough to read on every request.

    The copy is kept fresh by `/api/webhooks/stripe`, which is the *only* writer
    of the Stripe-owned columns below. Nothing in a request path may set them —
    if the app could mark itself premium, the subscription state would stop
    meaning "Stripe agrees this person paid".

    **Why a row can exist with no subscription.** A Stripe Customer is created
    when someone first opens checkout; the Subscription only exists once payment
    succeeds. Remembering the customer id in between is what stops a user who
    abandons checkout and returns from accumulating duplicate Stripe customers,
    each with their own payment methods and invoice history. So
    `stripe_customer_id` is set at checkout time and the subscription columns
    stay NULL until Stripe says otherwise — that is the normal state of a free
    user who once glanced at the upgrade page, not an error.
    """

    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Stripe's customer handle (`cus_...`). Set when we first send someone to
    # checkout, and never changed afterwards — it is the durable link between a
    # FitMind account and its billing history.
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # The subscription itself (`sub_...`). NULL until one exists. Retained after
    # cancellation rather than cleared: Stripe keeps the object, and dropping our
    # reference would make a past subscription unauditable from this side.
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))

    # Stripe's status vocabulary: incomplete, incomplete_expired, trialing,
    # active, past_due, canceled, unpaid, paused.
    #
    # Deliberately a String and not a native PG enum, which is what every other
    # controlled vocabulary in this schema uses (see `models/enums.py`). The
    # difference is who owns the vocabulary. Ours change when we decide they do;
    # this one changes when Stripe ships a new status, and an unrecognised value
    # arriving at an enum column would make the webhook write *fail*. That
    # failure mode is the bad one: we would silently keep serving the last known
    # state while Stripe went on billing — or not billing — the customer. A
    # string accepts whatever Stripe sends, and `entitlements` decides what the
    # unknown value is worth.
    status: Mapped[str | None] = mapped_column(String(50))

    # Which Price they are on. Stored so a subscription created against an old
    # price is still identifiable after `STRIPE_PRICE_ID` moves on.
    price_id: Mapped[str | None] = mapped_column(String(255))

    # End of the paid period. This is for *display* — "renews on", "access until"
    # — and is not consulted when deciding entitlement. It cannot be: if a
    # webhook were ever missed this column would be exactly as stale as `status`,
    # so treating it as a safety net would be a comforting fiction rather than a
    # second opinion.
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when the user cancels but has already paid through the period. The
    # status stays `active` throughout, so without this the settings page would
    # cheerfully tell someone who just cancelled that their plan renews.
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    user: Mapped["User"] = relationship(back_populates="subscription")

    __table_args__ = (
        # One billing relationship per user. The UNIQUE constraint is what makes
        # the 1:1 real; without it a webhook race could leave two rows and every
        # entitlement read would be a coin toss over which one it found.
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        # Two accounts sharing a Stripe customer would let one user's payment
        # entitle another. Unique here makes that unrepresentable rather than
        # merely unlikely.
        UniqueConstraint("stripe_customer_id", name="uq_subscriptions_stripe_customer_id"),
        UniqueConstraint(
            "stripe_subscription_id", name="uq_subscriptions_stripe_subscription_id"
        ),
        # A subscription id with no status is a subscription we know nothing
        # about; a status with no subscription id is a status belonging to
        # nothing. Neither is a state the webhook can legitimately produce, so
        # neither is storable. (Same pairing idea as `ai_analyses`'
        # narrative/model constraint.)
        CheckConstraint(
            "(stripe_subscription_id IS NULL) = (status IS NULL)",
            name="subscription_status_together",
        ),
        # No explicit indexes. All three lookups this table serves — by user (the
        # entitlement read), by customer id and by subscription id (both webhook
        # paths) — are already covered by the btrees backing the UNIQUE
        # constraints above. See docs/database.md on not paying twice for the
        # same index.
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} user_id={self.user_id} status={self.status!r}>"
        )
