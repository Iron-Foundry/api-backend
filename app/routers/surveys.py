"""Surveys router — member-facing endpoints for survey and application templates."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyActive, SurveyResponse, SurveyTemplate, User, WebSurveySubmission
from app.dependencies import get_current_user, get_session

router = APIRouter(prefix="/surveys", tags=["surveys"])

_DISCORD_ROLE_ORDER = [
    "Guest", "Achiever", "Sapphire", "Emerald", "Ruby",
    "Diamond", "Dragonstone", "Onyx", "Zenyte",
    "Ex-Moderator", "Mentor", "Event Team", "Moderator",
    "Senior Moderator", "Deputy Owner", "Co-owner",
]

# Minimum non-staff visibility options (must stay in role order)
_VISIBILITY_OPTIONS = ["Mentor", "Event Team", "Moderator"]


def _has_min_rank(discord_roles: list[str], min_role: str) -> bool:
    try:
        min_idx = _DISCORD_ROLE_ORDER.index(min_role)
    except ValueError:
        return False
    for role in discord_roles:
        if role in _DISCORD_ROLE_ORDER and _DISCORD_ROLE_ORDER.index(role) >= min_idx:
            return True
    return False


async def _get_roles(current_user: dict, session: AsyncSession) -> list[str]:
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(User.discord_roles).where(User.discord_user_id == discord_user_id)
    )
    roles = result.scalar_one_or_none()
    return roles or []


def _extract_fields(raw: list | dict) -> list[dict]:
    """Extract field list from questions JSONB (handles both list and dict formats)."""
    if isinstance(raw, list):
        return raw
    return raw.get("fields", [])


async def _list_templates(
    category: str, roles: list[str], discord_user_id: int, session: AsyncSession
) -> list[dict]:
    """Return templates of the given category visible to the user."""
    is_staff = _has_min_rank(roles, "Mentor")

    active_result = await session.execute(select(SurveyActive))
    active_row = active_result.scalar_one_or_none()
    active_template_id = active_row.template_id if active_row else None

    count_result = await session.execute(
        select(SurveyResponse.template_id, func.count().label("count")).group_by(
            SurveyResponse.template_id
        )
    )
    response_counts: dict[str, int] = {r.template_id: r.count for r in count_result}

    # Web submissions for this user
    sub_result = await session.execute(
        select(WebSurveySubmission.template_id).where(
            WebSurveySubmission.discord_user_id == discord_user_id
        )
    )
    submitted_set: set[str] = {r.template_id for r in sub_result}

    result = await session.execute(select(SurveyTemplate))
    rows = result.scalars().all()

    out: list[dict] = []
    for row in rows:
        raw = row.questions or {}
        if isinstance(raw, list):
            row_category = "survey"
            visibility: str | None = None
            description = None
        else:
            row_category = raw.get("category", "survey")
            visibility = raw.get("visibility")
            description = raw.get("description")

        if row_category != category:
            continue

        # Non-staff: show open templates they're eligible for + closed templates with prior submission
        if not is_staff:
            eligible = visibility is not None and _has_min_rank(roles, visibility)
            has_submission = row.template_id in submitted_set
            if not eligible and not has_submission:
                continue

        entry: dict = {
            "template_id": row.template_id,
            "title": row.title,
            "description": description,
            "visibility": visibility,
            "category": row_category,
            "is_active": row.template_id == active_template_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "user_submitted": row.template_id in submitted_set,
        }
        if is_staff:
            entry["response_count"] = response_counts.get(row.template_id, 0)
        out.append(entry)

    return out


@router.get("")
async def list_surveys(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List survey templates visible to the current user."""
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)
    return await _list_templates("survey", roles, discord_user_id, session)


@router.get("/applications")
async def list_applications(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List application templates visible to the current user."""
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)
    return await _list_templates("application", roles, discord_user_id, session)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get full template details including questions. Gated by visibility or prior submission."""
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)
    is_staff = _has_min_rank(roles, "Mentor")

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    if isinstance(raw, list):
        visibility: str | None = None
        description = None
        category = "survey"
    else:
        visibility = raw.get("visibility")
        description = raw.get("description")
        category = raw.get("category", "survey")

    # Fetch prior web submission
    sub_result = await session.execute(
        select(WebSurveySubmission).where(
            WebSurveySubmission.template_id == template_id,
            WebSurveySubmission.discord_user_id == discord_user_id,
        )
    )
    prior_sub = sub_result.scalar_one_or_none()

    # Non-staff: need visibility match OR prior submission
    if not is_staff:
        eligible = visibility is not None and _has_min_rank(roles, visibility)
        if not eligible and prior_sub is None:
            raise HTTPException(status_code=403, detail="Not authorized to view this template.")

    active_result = await session.execute(select(SurveyActive))
    active_row = active_result.scalar_one_or_none()
    is_active = active_row.template_id == template_id if active_row else False

    fields = _extract_fields(raw)
    return {
        "template_id": row.template_id,
        "title": row.title,
        "description": description,
        "visibility": visibility,
        "category": category,
        "is_active": is_active,
        "fields": fields,
        "user_submission": prior_sub.answers if prior_sub else None,
    }


class SubmitResponseBody(BaseModel):
    answers: dict


@router.post("/{template_id}/responses", status_code=201)
async def submit_response(
    template_id: str,
    body: SubmitResponseBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Submit a web response for a template. Template must be open and user eligible."""
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    if isinstance(raw, list):
        visibility: str | None = None
    else:
        visibility = raw.get("visibility")

    # Must be open
    if visibility is None:
        raise HTTPException(
            status_code=403, detail="This template is not currently accepting responses."
        )

    # Must be eligible (staff bypass)
    is_staff = _has_min_rank(roles, "Mentor")
    if not is_staff and not _has_min_rank(roles, visibility):
        raise HTTPException(status_code=403, detail="Not authorized to submit this template.")

    # Check for duplicate
    existing = await session.execute(
        select(WebSurveySubmission).where(
            WebSurveySubmission.template_id == template_id,
            WebSurveySubmission.discord_user_id == discord_user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="You have already submitted a response.")

    # Validate required fields
    fields = _extract_fields(raw)
    missing = [f["id"] for f in fields if f.get("required") and f["id"] not in body.answers]
    if missing:
        raise HTTPException(status_code=422, detail={"missing_required": missing})

    submission = WebSurveySubmission(
        template_id=template_id,
        discord_user_id=discord_user_id,
        answers=body.answers,
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(submission)
    await session.commit()

    return {"template_id": template_id, "submitted": True}


class VisibilityUpdate(BaseModel):
    """Payload for updating template visibility."""

    visibility: str | None  # None = staff only; else a Discord role name from _VISIBILITY_OPTIONS


@router.patch("/{template_id}/visibility")
async def set_visibility(
    template_id: str,
    body: VisibilityUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set visibility for a template. Requires Senior Moderator or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(
            status_code=403, detail="Requires Senior Moderator or higher."
        )

    if body.visibility is not None and body.visibility not in _VISIBILITY_OPTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"visibility must be one of {_VISIBILITY_OPTIONS} or null.",
        )

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    if isinstance(raw, list):
        updated: dict = {"fields": raw, "visibility": body.visibility}
    else:
        updated = {**raw, "visibility": body.visibility}

    await session.execute(
        update(SurveyTemplate)
        .where(SurveyTemplate.template_id == template_id)
        .values(questions=updated)
    )
    await session.commit()

    return {"template_id": template_id, "visibility": body.visibility}
