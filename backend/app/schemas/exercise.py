"""Exercise catalog schemas — read-only over the API (the catalog is seed data)."""

from __future__ import annotations

import uuid

from app.models.enums import Equipment, MuscleGroup
from app.schemas.common import ORMModel


class ExerciseRead(ORMModel):
    id: uuid.UUID
    name: str
    primary_muscle_group: MuscleGroup
    equipment: Equipment
    is_compound: bool
    instructions: str | None
