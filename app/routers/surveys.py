"""Surveys router — member-facing endpoints for survey and application templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyActive, SurveyResponse, SurveyTemplate, User
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


async def _list_templates(
    category: str, roles: list[str], session: AsyncSession
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

        # Non-staff only see templates explicitly made visible to their role
        if not is_staff:
            if visibility is None or not _has_min_rank(roles, visibility):
                continue

        entry: dict = {
            "template_id": row.template_id,
            "title": row.title,
            "description": description,
            "visibility": visibility,
            "category": row_category,
            "is_active": row.template_id == active_template_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
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
    roles = await _get_roles(current_user, session)
    return await _list_templates("survey", roles, session)


@router.get("/applications")
async def list_applications(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List application templates visible to the current user."""
    roles = await _get_roles(current_user, session)
    return await _list_templates("application", roles, session)


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

    # Merge visibility into the questions JSONB via SQL to avoid ORM mutation issues
    await session.execute(
        text(
            "UPDATE survey_templates"
            " SET questions = CASE"
            "   WHEN jsonb_typeof(questions) = 'array'"
            "   THEN jsonb_build_object('fields', questions, 'visibility', :vis::text)"
            "   ELSE questions || jsonb_build_object('visibility', :vis::text)"
            " END"
            " WHERE template_id = :tid"
        ),
        {"vis": body.visibility, "tid": template_id},
    )
    await session.commit()

    return {"template_id": template_id, "visibility": body.visibility}
