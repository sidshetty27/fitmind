"""`/api/billing` — starting a subscription and managing one.

Two redirects and nothing else. Both endpoints create a Stripe-hosted session and
hand back its URL; the frontend's whole job is to navigate there. No card data,
no payment intent, no client secret, and no Stripe.js — which is why there is no
publishable key anywhere in this project.

**Neither endpoint grants anything.** Completing a checkout does not make a user
premium; the `customer.subscription.created` webhook does, when Stripe confirms
money moved. That separation is deliberate: the success URL is just a page the
browser is sent to, and anyone can visit it directly. If arriving there conferred
premium, the paywall would be one address-bar edit deep.

The consequence is a real, small window — Stripe redirects the user back a beat
before the webhook lands, so the settings page can still say "Free" for a second
after a successful payment. That is a UI problem, solved in the UI. The
alternative trades it for a security hole.
"""

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import entitlements, stripe_client
from app.core.auth import get_current_user
from app.core.config import settings
from app.crud import subscription as subscription_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import CheckoutSessionRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _require_billing_configured() -> None:
    """503 when this deployment cannot sell anything.

    A configuration problem, not a client one — the request was perfectly valid.
    The UI reads `billing_enabled` from `/api/me/subscription` and hides the
    upgrade path entirely, so reaching this is either a stale page or a direct
    API call.
    """
    if not settings.billing_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured on this deployment",
        )


async def _customer_id_for(db: AsyncSession, user: User) -> str:
    """The user's Stripe customer id, creating one only if they have none.

    Reuse is the whole point. A second customer for someone who has bought
    before splits their invoices, payment methods, and subscription history
    across two records that nothing joins — and support can then only find one
    of them.

    The create-then-link order matters. `link_customer` is INSERT ... ON CONFLICT
    DO NOTHING, so if two clicks race, one of them loses and gets back the row
    the other wrote. We then use *that* row's customer id rather than the one we
    just created, so both requests check out against the same customer. The
    losing request leaves an unused customer at Stripe, which is harmless — it
    has no subscription and no charge — but it is logged, because a pile of them
    means something is retrying that should not be.
    """
    existing = await subscription_crud.get_by_user_id(db, user_id=user.id)
    if existing is not None:
        return existing.stripe_customer_id

    customer_id = await stripe_client.create_customer(
        email=user.email, user_id=str(user.id), name=user.name
    )
    linked = await subscription_crud.link_customer(
        db, user_id=user.id, stripe_customer_id=customer_id
    )

    if linked.stripe_customer_id != customer_id:
        logger.warning(
            "Raced another checkout for user %s; using existing customer %s and "
            "abandoning the one just created (%s)",
            user.id,
            linked.stripe_customer_id,
            customer_id,
        )

    return linked.stripe_customer_id


@router.post("/checkout", response_model=CheckoutSessionRead)
async def create_checkout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    """Start a subscription. Returns the hosted checkout URL to redirect to."""
    _require_billing_configured()

    subscription = await subscription_crud.get_by_user_id(db, user_id=current_user.id)
    if entitlements.is_premium(subscription):
        # Not an error state worth a stack trace, but it must not proceed: a
        # second checkout would open a second subscription against the same
        # customer and bill them twice. The frontend shows "Manage billing"
        # instead, so this is a stale page or a direct call.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active subscription",
        )

    customer_id = await _customer_id_for(db, current_user)

    try:
        url = await stripe_client.create_checkout_session(
            customer_id=customer_id,
            price_id=settings.stripe_price_id or "",
            success_url=f"{settings.frontend_url}/dashboard/settings?checkout=success",
            cancel_url=f"{settings.frontend_url}/dashboard/settings?checkout=cancelled",
        )
    except stripe.StripeError as exc:
        # Includes the common setup mistake of putting a `prod_...` in
        # STRIPE_PRICE_ID, which Stripe rejects with a clear message that is
        # worth having in the log rather than only in a 502 body.
        logger.error("Could not create checkout session for %s: %s", customer_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start checkout. Please try again.",
        ) from exc

    return CheckoutSessionRead(url=url)


@router.post("/portal", response_model=CheckoutSessionRead)
async def create_portal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    """Open Stripe's billing portal — cancel, change card, download invoices."""
    _require_billing_configured()

    subscription = await subscription_crud.get_by_user_id(db, user_id=current_user.id)
    if subscription is None:
        # Nothing to manage. Deliberately not "create a customer so the portal
        # opens": it would show an empty portal to someone who has never paid,
        # which answers no question they had.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing account for this user",
        )

    try:
        url = await stripe_client.create_portal_session(
            customer_id=subscription.stripe_customer_id,
            return_url=f"{settings.frontend_url}/dashboard/settings",
        )
    except stripe.StripeError as exc:
        logger.error(
            "Could not create portal session for %s: %s",
            subscription.stripe_customer_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not open the billing portal. Please try again.",
        ) from exc

    return CheckoutSessionRead(url=url)
