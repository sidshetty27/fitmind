"""User profile schemas — the `/api/me` contract.

Note what is absent from `UserRead`: `clerk_id`. It is an internal join key to
another system; exposing it in the API would invite clients to couple to Clerk's
identifier format, which is exactly the coupling `users.id` exists to prevent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ExperienceLevel, Goal
from app.schemas.common import ORMModel, PositiveDecimal


class UserRead(ORMModel):
    id: uuid.UUID
    email: str
    name: str | None
    height_cm: Decimal | None
    weight_kg: Decimal | None
    goal: Goal | None
    experience_level: ExperienceLevel | None
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Partial profile update (PATCH).

    Every field is optional so a client can send just the one it is changing. The
    handler applies only fields that were *explicitly provided* (`exclude_unset`),
    so omitting `name` leaves it untouched — distinct from sending `name: null`,
    which clears it.
    """

    name: str | None = None
    height_cm: PositiveDecimal | None = None
    weight_kg: PositiveDecimal | None = None
    goal: Goal | None = None
    experience_level: ExperienceLevel | None = None
