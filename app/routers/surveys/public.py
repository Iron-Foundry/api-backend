from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyActive, SurveyTemplate, WebSurveySubmission
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission

from ._helpers import (
    extract_fields,
    extract_is_open,
    get_roles,
    list_templates,
    normalize_visibility,
)

router = APIRouter()


class SubmitResponseBody(BaseModel):
    answers: dict


@router.get("/")
async def list_surveys(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    roles = await get_roles(current_user, session)
    return await list_templates("survey", roles, discord_user_id, session)


@router.get("/applications")
async def list_applications(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    roles = await get_roles(current_user, session)
    return await list_templates("application", roles, discord_user_id, session)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    discord_user_id = int(current_user["sub"])
    roles = await get_roles(current_user, session)
    is_staff = await check_page_permission("staff.surveys", "read", roles, session)

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    if isinstance(raw, list):
        visibility, description, category = None, None, "survey"
    else:
        visibility = normalize_visibility(raw.get("visibility"))
        description = raw.get("description")
        category = raw.get("category", "survey")

    is_open = extract_is_open(raw)

    prior_sub = (
        await session.execute(
            select(WebSurveySubmission).where(
                WebSurveySubmission.template_id == template_id,
                WebSurveySubmission.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none()

    if not is_staff and not is_open and prior_sub is None:
        raise HTTPException(403, "Not authorized to view this template.")

    active_row = (await session.execute(select(SurveyActive))).scalar_one_or_none()
    is_active = active_row.template_id == template_id if active_row else False

    return {
        "template_id": row.template_id,
        "title": row.title,
        "description": description,
        "is_open": is_open,
        "visibility": visibility,
        "category": category,
        "is_active": is_active,
        "fields": extract_fields(raw),
        "user_submission": prior_sub.answers if prior_sub else None,
    }


@router.post("/{template_id}/responses", status_code=201)
async def submit_response(
    template_id: str,
    body: SubmitResponseBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Submit a web response. Survey must be open; any authenticated member may respond."""
    discord_user_id = int(current_user["sub"])

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    if not extract_is_open(raw):
        raise HTTPException(403, "This survey is not currently accepting responses.")

    if (
        await session.execute(
            select(WebSurveySubmission).where(
                WebSurveySubmission.template_id == template_id,
                WebSurveySubmission.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none() is not None:
        raise HTTPException(409, "You have already submitted a response.")

    fields = extract_fields(raw)
    missing = [
        f["id"] for f in fields if f.get("required") and f["id"] not in body.answers
    ]
    if missing:
        raise HTTPException(422, {"missing_required": missing})

    session.add(
        WebSurveySubmission(
            template_id=template_id,
            discord_user_id=discord_user_id,
            answers=body.answers,
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return {"template_id": template_id, "submitted": True}
