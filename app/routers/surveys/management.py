from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyTemplate
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission

from ._helpers import extract_is_open, get_roles

router = APIRouter()


class OpenUpdate(BaseModel):
    is_open: bool


class VisibilityUpdate(BaseModel):
    visibility: list[str] | None


class TemplateFieldBody(BaseModel):
    id: str
    type: str
    label: str
    description: str | None = None
    required: bool = False
    options: list[str] = []
    max_choices: int = Field(default=1, ge=1)


class TemplateBody(BaseModel):
    title: str
    category: str = "survey"
    description: str | None = None
    fields: list[TemplateFieldBody] = []


async def _require_survey_edit(current_user: dict, session: AsyncSession) -> None:
    roles = await get_roles(current_user, session)
    if not await check_page_permission("staff.surveys", "edit", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")


@router.patch("/{template_id}/open")
async def set_open(
    template_id: str,
    body: OpenUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Publish or close a survey. Requires Senior Moderator or higher."""
    await _require_survey_edit(current_user, session)

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    updated: dict = (
        {"fields": raw, "is_open": body.is_open}
        if isinstance(raw, list)
        else {**raw, "is_open": body.is_open}
    )
    await session.execute(
        update(SurveyTemplate)
        .where(SurveyTemplate.template_id == template_id)
        .values(questions=updated)
    )
    await session.commit()
    return {"template_id": template_id, "is_open": body.is_open}


@router.patch("/{template_id}/visibility")
async def set_visibility(
    template_id: str,
    body: VisibilityUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set which roles can read responses. Requires Senior Moderator or higher."""
    await _require_survey_edit(current_user, session)

    if body.visibility is not None and len(body.visibility) == 0:
        body.visibility = None

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    updated = (
        {"fields": raw, "visibility": body.visibility}
        if isinstance(raw, list)
        else {**raw, "visibility": body.visibility}
    )
    await session.execute(
        update(SurveyTemplate)
        .where(SurveyTemplate.template_id == template_id)
        .values(questions=updated)
    )
    await session.commit()
    return {"template_id": template_id, "visibility": body.visibility}


@router.post("/", status_code=201)
async def create_template(
    body: TemplateBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new survey/application template. Requires Senior Moderator or higher."""
    roles = await get_roles(current_user, session)
    if not await check_page_permission("staff.surveys", "create", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")

    template_id = uuid.uuid4().hex[:16]
    questions: dict = {
        "category": body.category,
        "description": body.description,
        "fields": [f.model_dump() for f in body.fields],
        "is_open": False,
        "visibility": None,
    }
    now = datetime.now(timezone.utc)
    session.add(
        SurveyTemplate(
            template_id=template_id,
            title=body.title,
            questions=questions,
            created_at=now,
        )
    )
    await session.commit()

    return {
        "template_id": template_id,
        "title": body.title,
        "category": body.category,
        "description": body.description,
        "is_open": False,
        "visibility": None,
        "is_active": False,
        "response_count": 0,
        "web_response_count": 0,
        "user_submitted": False,
        "created_at": now.isoformat(),
    }


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a template's title, category, description, and fields. Requires Senior Moderator or higher."""
    await _require_survey_edit(current_user, session)

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    is_open = extract_is_open(raw)
    visibility = None if isinstance(raw, list) else raw.get("visibility")

    updated: dict = {
        "category": body.category,
        "description": body.description,
        "fields": [f.model_dump() for f in body.fields],
        "is_open": is_open,
        "visibility": visibility,
    }
    await session.execute(
        update(SurveyTemplate)
        .where(SurveyTemplate.template_id == template_id)
        .values(title=body.title, questions=updated)
    )
    await session.commit()

    return {
        "template_id": template_id,
        "title": body.title,
        "category": body.category,
        "description": body.description,
        "is_open": is_open,
        "visibility": visibility,
    }
