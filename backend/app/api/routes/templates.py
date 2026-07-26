"""`/api/templates` — reusable workout plans. Every route is user-scoped.

Same access-control shape as `/api/workouts`: `get_current_user` supplies the id,
every CRUD call filters by it, and a template that is not the caller's returns 404
rather than 403 — the API never confirms that someone else's template exists.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.crud import template as template_crud
from app.crud.template import DuplicateTemplateNameError
from app.crud.workout import UnknownExerciseError
from app.db.session import get_db
from app.models.user import User
from app.models.workout_template import WorkoutTemplate
from app.schemas.template import (
    TemplateApply,
    TemplateCreate,
    TemplateExercisesReplace,
    TemplateListItem,
    TemplateRead,
    TemplateUpdate,
)
from app.schemas.workout import WorkoutRead

router = APIRouter(prefix="/api/templates", tags=["templates"])

_UNKNOWN_EXERCISE = status.HTTP_422_UNPROCESSABLE_ENTITY
# 409, not 422: the payload is well-formed, it just conflicts with a row that
# already exists. That distinction lets the client tell "you typed something
# invalid" apart from "that name is taken".
_DUPLICATE_NAME = status.HTTP_409_CONFLICT


async def _get_owned_or_404(
    db: AsyncSession, user: User, template_id: uuid.UUID
) -> WorkoutTemplate:
    """Load a template the caller owns, or raise 404. The one ownership gate."""
    template = await template_crud.get_template(
        db, user_id=user.id, template_id=template_id
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    return template


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await template_crud.create_template(db, user_id=current_user.id, data=data)
    except UnknownExerciseError as exc:
        raise HTTPException(status_code=_UNKNOWN_EXERCISE, detail=str(exc)) from exc
    except DuplicateTemplateNameError as exc:
        raise HTTPException(status_code=_DUPLICATE_NAME, detail=str(exc)) from exc


@router.get("", response_model=list[TemplateListItem])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateListItem]:
    rows = await template_crud.list_templates(db, user_id=current_user.id)
    # `exercise_count` is an aggregate column, not a model attribute, so these are
    # built explicitly rather than via from_attributes.
    return [
        TemplateListItem(
            id=t.id,
            name=t.name,
            description=t.description,
            exercise_count=count,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t, count in rows
    ]


@router.get("/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_or_404(db, current_user, template_id)


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await _get_owned_or_404(db, current_user, template_id)
    try:
        return await template_crud.update_template(db, template=template, data=data)
    except DuplicateTemplateNameError as exc:
        raise HTTPException(status_code=_DUPLICATE_NAME, detail=str(exc)) from exc


@router.put("/{template_id}/exercises", response_model=TemplateRead)
async def replace_template_exercises(
    template_id: uuid.UUID,
    data: TemplateExercisesReplace,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace a template's entire exercise list in one atomic operation."""
    template = await _get_owned_or_404(db, current_user, template_id)
    try:
        return await template_crud.replace_template_exercises(
            db, template=template, data=data
        )
    except UnknownExerciseError as exc:
        raise HTTPException(status_code=_UNKNOWN_EXERCISE, detail=str(exc)) from exc


@router.post(
    "/{template_id}/apply",
    response_model=WorkoutRead,
    status_code=status.HTTP_201_CREATED,
)
async def apply_template(
    template_id: uuid.UUID,
    data: TemplateApply,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log a workout from this template.

    Returns the new **workout**, not the template — the caller's next move is to
    open the session and adjust the numbers they actually hit.
    """
    template = await _get_owned_or_404(db, current_user, template_id)
    try:
        return await template_crud.apply_template(
            db, user_id=current_user.id, template=template, data=data
        )
    except UnknownExerciseError as exc:
        # Reachable if a catalog entry was retired between saving and applying.
        raise HTTPException(status_code=_UNKNOWN_EXERCISE, detail=str(exc)) from exc


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    template = await _get_owned_or_404(db, current_user, template_id)
    await template_crud.delete_template(db, template=template)
