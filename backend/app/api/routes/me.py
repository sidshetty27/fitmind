"""`/api/me` — the authenticated user's own profile.

There is no `/users/{id}` here on purpose: a client never addresses a user by id,
it only ever asks about *itself*, and "me" is resolved from the token. That closes
off a whole class of broken-access-control bugs — there is simply no id to tamper
with.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import user as user_crud
from app.db.session import get_db
from app.models.user import User
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
