"""`/api/me` — the authenticated user's own profile.

There is no `/users/{id}` here on purpose: a client never addresses a user by id,
it only ever asks about *itself*, and "me" is resolved from the token. That closes
off a whole class of broken-access-control bugs — there is simply no id to tamper
with.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import entitlements
from app.core.auth import get_current_user
from app.core.config import settings
from app.crud import subscription as subscription_crud
from app.crud import user as user_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import SubscriptionRead
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the signed-in user's profile (JIT-provisioned on first call)."""
    return current_user


@router.patch("", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update the signed-in user's own profile fields."""
    return await user_crud.update_user_profile(db, user=current_user, data=data)


@router.get("/subscription", response_model=SubscriptionRead)
async def read_my_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRead:
    """The signed-in user's plan and AI allowance.

    Lives under `/api/me` rather than `/api/billing` because it answers a
    question about *the user*, not about a payment: what am I allowed to do. The
    billing router is for the two actions that talk to Stripe.

    One endpoint serves both the settings page and the Coach page. Two would
    eventually disagree about whether someone is premium, and the one that
    disagreed would be whichever was not updated.
    """
    subscription = await subscription_crud.get_by_user_id(db, user_id=current_user.id)
    quota = await entitlements.quota_state(db, user=current_user)

    return SubscriptionRead(
        premium=quota.premium,
        status=subscription.status if subscription else None,
        current_period_end=subscription.current_period_end if subscription else None,
        cancel_at_period_end=(
            subscription.cancel_at_period_end if subscription else False
        ),
        billing_enabled=settings.billing_enabled,
        has_billing_account=subscription is not None,
        ai_limit=quota.limit,
        ai_used=quota.used,
        ai_remaining=quota.remaining,
        ai_resets_at=quota.resets_at,
    )
