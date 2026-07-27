from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    SurveyResponse,
    SurveyTemplate,
    Ticket,
    User,
    WebSurveySubmission,
)
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission, get_admin_bypass_roles
from app.services.rank_mappings import get_role_label_map

from ._helpers import get_roles

router = APIRouter()


@router.get("/{template_id}/responses")
async def get_template_responses(
    template_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all submissions for a template. Access gated by template visibility setting."""
    roles = await get_roles(current_user, session)

    row = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.template_id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Template not found.")

    raw = row.questions or {}
    raw_visibility = None if isinstance(raw, list) else raw.get("visibility")

    bypass_roles = await get_admin_bypass_roles(session)
    is_bypass = any(r in bypass_roles for r in roles)

    role_labels: set[str] = set()
    if not is_bypass:
        id_to_label = await get_role_label_map(session)
        role_labels = {id_to_label.get(r, r) for r in roles}

    if raw_visibility is None:
        if not (
            is_bypass
            or await check_page_permission("staff.surveys", "edit", roles, session)
        ):
            raise HTTPException(403, "Requires Senior Moderator or higher.")
    else:
        allowed_set: set[str] = (
            {raw_visibility} if isinstance(raw_visibility, str) else set(raw_visibility)
        )
        if not (
            is_bypass
            or any(r in allowed_set for r in roles)
            or role_labels & allowed_set
        ):
            raise HTTPException(
                403, "You do not have permission to view responses for this survey."
            )

    out: list[dict[str, Any]] = []

    for sub, user in await session.execute(
        select(WebSurveySubmission, User)
        .join(
            User,
            User.discord_user_id == WebSurveySubmission.discord_user_id,
            isouter=True,
        )
        .where(WebSurveySubmission.template_id == template_id)
    ):
        out.append(
            {
                "id": f"web_{sub.id}",
                "source": "web",
                "discord_user_id": sub.discord_user_id,
                "discord_username": user.discord_username if user else None,
                "rsn": user.rsn if user else None,
                "discord_roles": user.discord_roles if user else [],
                "answers": sub.answers,
                "submitted_at": sub.submitted_at.isoformat()
                if sub.submitted_at
                else None,
            }
        )

    for resp, ticket, user in await session.execute(
        select(SurveyResponse, Ticket, User)
        .join(Ticket, Ticket.ticket_id == SurveyResponse.ticket_id)
        .join(User, User.discord_user_id == Ticket.creator_id, isouter=True)
        .where(SurveyResponse.template_id == template_id)
    ):
        raw_resp: dict[str, Any] = resp.responses or {}
        answers = raw_resp.get("answers") or {} if "ticket_id" in raw_resp else raw_resp
        out.append(
            {
                "id": f"discord_{resp.ticket_id}",
                "source": "discord",
                "discord_user_id": ticket.creator_id,
                "discord_username": user.discord_username
                if user
                else ticket.creator_name,
                "rsn": user.rsn if user else None,
                "discord_roles": user.discord_roles if user else [],
                "answers": answers,
                "submitted_at": resp.submitted_at.isoformat()
                if resp.submitted_at
                else None,
            }
        )

    out.sort(key=lambda r: r["submitted_at"] or "", reverse=True)
    return out
