"""Shapes for stored AI coach runs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import NonNegativeInt, ORMModel


class FindingRead(BaseModel):
    """One deterministic observation, exactly as it was computed and stored.

    `statement` is already a complete, true sentence — the UI renders it directly
    when there is no narrative, so a findings-only analysis reads as finished
    rather than as raw data.
    """

    kind: str
    subject: str
    statement: str
    detail: dict[str, Any] = Field(default_factory=dict)


class AiAnalysisRead(ORMModel):
    """A stored analysis.

    `narrative` and `model` are null together whenever the coaching voice was
    unavailable — no API key, over quota, or a failed call. That is a complete
    analysis with findings only, not a failed one, and clients should render it
    as such rather than showing an error.
    """

    id: uuid.UUID
    window_start: date
    window_end: date
    workout_count: NonNegativeInt
    findings: list[FindingRead] = Field(default_factory=list)
    narrative: str | None = None
    model: str | None = None
    created_at: datetime


class AiAnalysisListItem(ORMModel):
    """A row in the coaching history — enough to render without the full findings."""

    id: uuid.UUID
    window_start: date
    window_end: date
    workout_count: NonNegativeInt
    finding_count: NonNegativeInt
    has_narrative: bool
    created_at: datetime


__all__ = ["AiAnalysisListItem", "AiAnalysisRead", "FindingRead"]
