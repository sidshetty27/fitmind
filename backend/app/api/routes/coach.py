"""`/api/coach` — the AI coach. User-scoped.

Running an analysis is a POST because it is not idempotent: it costs a model
call and writes a row. The row is the point — Phase 8's usage gate is a count of
these, and a user can re-read past coaching without paying for it again.

The findings half never fails. A model that is unconfigured, rate-limited, or
declining costs the response its `narrative`, not its `findings` — so this router
has no "AI unavailable" error path by design.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import coach as coach_ai
from app.analysis import findings as findings_engine
from app.core.auth import get_current_user
from app.core.config import settings
from app.crud import ai_analysis as analysis_crud
from app.crud import analysis as aggregation_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_analysis import AiAnalysisListItem, AiAnalysisRead

router = APIRouter(prefix="/api/coach", tags=["coach"])


@router.post("/analyses", response_model=AiAnalysisRead, status_code=status.HTTP_201_CREATED)
async def run_analysis(
    weeks: int | None = Query(
        default=None,
        ge=1,
        le=52,
        description="Trailing window to analyse; defaults to the configured window",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyse recent training, store the result, and return it.

    Uses `coaching_summary`, not `training_summary`: the latter caps movements by
    session count and would drop the least-trained ones, which are exactly what a
    neglect finding is about.
    """
    today = date.today()
    summary = await aggregation_crud.coaching_summary(
        db,
        user_id=current_user.id,
        today=today,
        weeks=weeks or settings.coach_window_weeks,
    )
    results = findings_engine.analyse(summary, today)
    narrative, model = coach_ai.generate_narrative(results)

    return await analysis_crud.create_analysis(
        db,
        user_id=current_user.id,
        window_start=summary.window_start,
        window_end=summary.window_end,
        workout_count=summary.workout_count,
        findings=[finding.as_dict() for finding in results],
        narrative=narrative,
        model=model,
    )


@router.get("/analyses", response_model=list[AiAnalysisListItem])
async def list_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """Past coaching, newest first. Summary rows — fetch one for its findings."""
    rows = await analysis_crud.list_analyses(
        db, user_id=current_user.id, limit=limit, offset=offset
    )
    return [
        AiAnalysisListItem(
            id=row.id,
            window_start=row.window_start,
            window_end=row.window_end,
            workout_count=row.workout_count,
            finding_count=len(row.findings),
            has_narrative=row.narrative is not None,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AiAnalysisRead)
async def get_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One stored analysis. 404 covers both unknown and not-yours, identically."""
    analysis = await analysis_crud.get_analysis(
        db, user_id=current_user.id, analysis_id=analysis_id
    )
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found"
        )
    return analysis
