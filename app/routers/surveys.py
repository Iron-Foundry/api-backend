"""Surveys router — member-facing endpoints for survey and application templates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyActive, SurveyResponse, SurveyTemplate, Ticket, User, WebSurveySubmission
from app.dependencies import get_current_user, get_session
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/surveys", tags=["surveys"])

_DISCORD_ROLE_ORDER = [
    "Guest", "Achiever", "Sapphire", "Emerald", "Ruby",
    "Diamond", "Dragonstone", "Onyx", "Zenyte",
    "Ex-Moderator", "Mentor", "Event Team", "Moderator",
    "Senior Moderator", "Deputy Owner", "Co-owner",
]

_VISIBILITY_OPTIONS = ["Mentor", "Event Team", "Moderator", "Senior Moderator"]


def _normalize_visibility(raw: str | list | None) -> list[str] | None:
    """Normalize visibility to a list of allowed roles (or None = senior staff only).

    Handles three stored formats:
    - None  → staff only
    - str   → legacy single min-rank (convert to one-item list for display, but
               callers that need the old min-rank semantic keep the raw value)
    - list  → new explicit-roles format
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    return raw


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
    return await get_effective_roles(discord_user_id, session)


def _extract_fields(raw: list | dict) -> list[dict]:
    fields: list[dict] = raw if isinstance(raw, list) else raw.get("fields", [])
    return [
        {**f, "label": f["text"]} if "label" not in f and "text" in f else f
        for f in fields
    ]


def _extract_is_open(raw: list | dict) -> bool:
    """Return whether the survey is currently accepting responses from all members.

    Precedence:
    1. Explicit ``is_open`` key in the JSONB dict (set via web staff panel).
    2. Backward-compat fallback: old templates have no ``is_open`` but used
       ``visibility != null`` to signal that the survey was published.
    """
    if isinstance(raw, list):
        return False  # legacy list-only format — treat as closed
    if "is_open" in raw:
        return bool(raw["is_open"])
    return raw.get("visibility") is not None


async def _list_templates(
    category: str, roles: list[str], discord_user_id: int, session: AsyncSession
) -> list[dict]:
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

    web_count_result = await session.execute(
        select(WebSurveySubmission.template_id, func.count().label("count")).group_by(
            WebSurveySubmission.template_id
        )
    )
    web_response_counts: dict[str, int] = {r.template_id: r.count for r in web_count_result}

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
            visibility: list[str] | None = None
            description = None
        else:
            row_category = raw.get("category", "survey")
            visibility = _normalize_visibility(raw.get("visibility"))
            description = raw.get("description")

        if row_category != category:
            continue

        is_open = _extract_is_open(raw)

        if not is_staff:
            has_submission = row.template_id in submitted_set
            if not is_open and not has_submission:
                continue

        entry: dict = {
            "template_id": row.template_id,
            "title": row.title,
            "description": description,
            "is_open": is_open,
            "visibility": visibility,
            "category": row_category,
            "is_active": row.template_id == active_template_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "user_submitted": row.template_id in submitted_set,
        }
        if is_staff:
            entry["response_count"] = response_counts.get(row.template_id, 0)
            entry["web_response_count"] = web_response_counts.get(row.template_id, 0)
        out.append(entry)

    return out


@router.get("")
async def list_surveys(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)
    return await _list_templates("survey", roles, discord_user_id, session)


@router.get("/applications")
async def list_applications(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    roles = await _get_roles(current_user, session)
    return await _list_templates("application", roles, discord_user_id, session)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
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
        visibility: list[str] | None = None
        description = None
        category = "survey"
    else:
        visibility = _normalize_visibility(raw.get("visibility"))
        description = raw.get("description")
        category = raw.get("category", "survey")

    is_open = _extract_is_open(raw)

    sub_result = await session.execute(
        select(WebSurveySubmission).where(
            WebSurveySubmission.template_id == template_id,
            WebSurveySubmission.discord_user_id == discord_user_id,
        )
    )
    prior_sub = sub_result.scalar_one_or_none()

    if not is_staff:
        if not is_open and prior_sub is None:
            raise HTTPException(status_code=403, detail="Not authorized to view this template.")

    active_result = await session.execute(select(SurveyActive))
    active_row = active_result.scalar_one_or_none()
    is_active = active_row.template_id == template_id if active_row else False

    fields = _extract_fields(raw)
    return {
        "template_id": row.template_id,
        "title": row.title,
        "description": description,
        "is_open": is_open,
        "visibility": visibility,
        "category": category,
        "is_active": is_active,
        "fields": fields,
        "user_submission": prior_sub.answers if prior_sub else None,
    }


@router.get("/{template_id}/responses")
async def get_template_responses(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List all submissions (web + Discord) for a template.

    Access is gated by the template's response_visibility setting.
    If visibility is null, requires Mentor+ (all staff). Otherwise requires
    the specified rank or higher.
    """
    roles = await _get_roles(current_user, session)

    template_result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = template_result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    raw_visibility = None if isinstance(raw, list) else raw.get("visibility")

    if raw_visibility is None:
        if not _has_min_rank(roles, "Senior Moderator"):
            raise HTTPException(status_code=403, detail="Requires Senior Moderator or higher.")
    elif isinstance(raw_visibility, str):
        if not _has_min_rank(roles, raw_visibility):
            raise HTTPException(
                status_code=403, detail=f"Requires {raw_visibility} or higher to view responses."
            )
    else:
        allowed: set[str] = set(raw_visibility)
        if not (_has_min_rank(roles, "Senior Moderator") or any(r in allowed for r in roles)):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of the following roles: {', '.join(sorted(allowed))}.",
            )

    web_result = await session.execute(
        select(WebSurveySubmission, User)
        .join(User, User.discord_user_id == WebSurveySubmission.discord_user_id, isouter=True)
        .where(WebSurveySubmission.template_id == template_id)
    )
    out: list[dict] = []
    for sub, user in web_result:
        out.append({
            "id": f"web_{sub.id}",
            "source": "web",
            "discord_user_id": sub.discord_user_id,
            "discord_username": user.discord_username if user else None,
            "rsn": user.rsn if user else None,
            "discord_roles": user.discord_roles if user else [],
            "answers": sub.answers,
            "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
        })

    discord_result = await session.execute(
        select(SurveyResponse, Ticket, User)
        .join(Ticket, Ticket.ticket_id == SurveyResponse.ticket_id)
        .join(User, User.discord_user_id == Ticket.creator_id, isouter=True)
        .where(SurveyResponse.template_id == template_id)
    )
    for resp, ticket, user in discord_result:
        raw_resp: dict = resp.responses or {}
        if "ticket_id" in raw_resp:
            answers = raw_resp.get("answers") or {}
        else:
            answers = raw_resp
        out.append({
            "id": f"discord_{resp.ticket_id}",
            "source": "discord",
            "discord_user_id": ticket.creator_id,
            "discord_username": user.discord_username if user else ticket.creator_name,
            "rsn": user.rsn if user else None,
            "discord_roles": user.discord_roles if user else [],
            "answers": answers,
            "submitted_at": resp.submitted_at.isoformat() if resp.submitted_at else None,
        })

    out.sort(key=lambda r: r["submitted_at"] or "", reverse=True)
    return out


class SubmitResponseBody(BaseModel):
    answers: dict


@router.post("/{template_id}/responses", status_code=201)
async def submit_response(
    template_id: str,
    body: SubmitResponseBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Submit a web response. Survey must be open; any authenticated member may respond."""
    discord_user_id = int(current_user["sub"])

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    if not _extract_is_open(raw):
        raise HTTPException(
            status_code=403, detail="This survey is not currently accepting responses."
        )

    existing = await session.execute(
        select(WebSurveySubmission).where(
            WebSurveySubmission.template_id == template_id,
            WebSurveySubmission.discord_user_id == discord_user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="You have already submitted a response.")

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


class OpenUpdate(BaseModel):
    is_open: bool


@router.patch("/{template_id}/open")
async def set_open(
    template_id: str,
    body: OpenUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Publish or close a survey. Requires Senior Moderator or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(
            status_code=403, detail="Requires Senior Moderator or higher."
        )

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    if isinstance(raw, list):
        updated: dict = {"fields": raw, "is_open": body.is_open}
    else:
        updated = {**raw, "is_open": body.is_open}

    await session.execute(
        update(SurveyTemplate)
        .where(SurveyTemplate.template_id == template_id)
        .values(questions=updated)
    )
    await session.commit()

    return {"template_id": template_id, "is_open": body.is_open}


class VisibilityUpdate(BaseModel):
    """Controls which roles can read responses for this template (null = Senior Moderator+ only)."""
    visibility: list[str] | None


@router.patch("/{template_id}/visibility")
async def set_visibility(
    template_id: str,
    body: VisibilityUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set which minimum staff rank can read responses. Requires Senior Moderator or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(
            status_code=403, detail="Requires Senior Moderator or higher."
        )

    if body.visibility is not None:
        invalid = [v for v in body.visibility if v not in _VISIBILITY_OPTIONS]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid roles: {invalid}. Must be from {_VISIBILITY_OPTIONS}.",
            )
        if len(body.visibility) == 0:
            body.visibility = None

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


class TemplateFieldBody(BaseModel):
    id: str
    type: str
    label: str
    description: str | None = None
    required: bool = False
    options: list[str] = []
    max_choices: int = 1


class TemplateBody(BaseModel):
    title: str
    category: str = "survey"
    description: str | None = None
    fields: list[TemplateFieldBody] = []


@router.post("", status_code=201)
async def create_template(
    body: TemplateBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new survey/application template. Requires Senior Moderator or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(
            status_code=403, detail="Requires Senior Moderator or higher."
        )

    template_id = uuid.uuid4().hex[:16]
    questions: dict = {
        "category": body.category,
        "description": body.description,
        "fields": [f.model_dump() for f in body.fields],
        "is_open": False,
        "visibility": None,
    }
    now = datetime.now(timezone.utc)
    row = SurveyTemplate(
        template_id=template_id,
        title=body.title,
        questions=questions,
        created_at=now,
    )
    session.add(row)
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
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(
            status_code=403, detail="Requires Senior Moderator or higher."
        )

    result = await session.execute(
        select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    raw = row.questions or {}
    is_open = _extract_is_open(raw)
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
