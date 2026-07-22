"""Progress-entry schemas — one body/lifestyle snapshot per day."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import (
    NonNegativeInt,
    ORMModel,
    PositiveDecimal,
    SleepHours,
)


class ProgressUpsert(BaseModel):
    """Create-or-update a day's entry.

    Modelled as an upsert because the table's natural key is
    `(user_id, recorded_on)`: "log today's weight" should be idempotent, not
    create a second row for the same day on a double-tap. Every metric is optional
    and independent — logging weight without macros is the common case.
    """

    recorded_on: date
    bodyweight_kg: PositiveDecimal | None = None
    calories: NonNegativeInt | None = None
    protein_g: NonNegativeInt | None = None
    sleep_hours: SleepHours | None = None
    notes: str | None = None


class ProgressRead(ORMModel):
    id: uuid.UUID
    recorded_on: date
    bodyweight_kg: Decimal | None
    calories: int | None
    protein_g: int | None
    sleep_hours: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
