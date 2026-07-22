"""Shared schema base and reusable constrained field types."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base for every *response* schema.

    `from_attributes=True` lets FastAPI build the schema straight from a SQLAlchemy
    ORM instance (reading attributes) instead of requiring a dict — so handlers can
    return the model object and let this layer shape the JSON.
    """

    model_config = ConfigDict(from_attributes=True)


# Reusable constrained numerics, mirroring the database CHECK constraints so the
# same rule is stated once at the edge and once (authoritatively) in the schema.
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, max_digits=6, decimal_places=2)]
NonNegativeWeight = Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=2)]
Rpe = Annotated[Decimal, Field(ge=1, le=10, max_digits=3, decimal_places=1)]
SleepHours = Annotated[Decimal, Field(ge=0, le=24, max_digits=3, decimal_places=1)]
