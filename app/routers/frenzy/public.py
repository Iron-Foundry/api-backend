"""The public view of the running frenzy event."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzySubmission, FrenzyTeam, FrenzyTemplate
from app.dependencies import get_optional_user, get_session

from ._progress import _apply_pending_submissions
from ._scoring import _compute_scores_from_progress, _compute_team_scores
from .signup_schemas import MyFrenzySignup
from .signups import find_signup

router = APIRouter()


async def _my_signup(
    session: AsyncSession, event_id: int, viewer: dict[str, Any] | None
) -> dict[str, Any] | None:
    if viewer is None:
        return None
    signup = await find_signup(session, event_id, int(viewer["sub"]))
    if signup is None:
        return None
    return MyFrenzySignup.model_validate(signup, from_attributes=True).model_dump(
        mode="json"
    )


@router.get("/active")
async def get_active_event(
    session: AsyncSession = Depends(get_session),
    viewer: dict[str, Any] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Return the active event with all teams ranked by total points.

    A signed-in caller also gets their own signup as `my_signup`.
    """
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(500, "Event template not found.")

    teams = (
        (
            await session.execute(
                select(FrenzyTeam)
                .where(FrenzyTeam.event_id == event.id)
                .order_by(FrenzyTeam.sort_order)
            )
        )
        .scalars()
        .all()
    )

    pending_by_team: dict[int, list[FrenzySubmission]] = {}
    pending_rows = (
        (
            await session.execute(
                select(FrenzySubmission).where(
                    FrenzySubmission.event_id == event.id,
                    FrenzySubmission.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    for sub in pending_rows:
        pending_by_team.setdefault(sub.team_id, []).append(sub)

    teams_out = []
    for team in teams:
        scores = _compute_team_scores(template, team)
        pending = pending_by_team.get(team.id, [])
        if pending:
            pi, pa, pm = _apply_pending_submissions(
                team.item_progress or {},
                team.activity_progress or {},
                team.milestone_progress or {},
                pending,
            )
            pending_points = (
                _compute_scores_from_progress(template, pi, pa, pm)["total"]
                - scores["total"]
            )
        else:
            pending_points = 0.0

        teams_out.append(
            {
                "id": team.id,
                "name": team.name,
                "slug": team.slug,
                "icon_url": team.icon_url,
                "sort_order": team.sort_order,
                "total_points": scores["total"],
                "pending_points": pending_points,
                "tier_points": scores["tier_points"],
                "activity_points": scores["activity_points"],
                "milestone_points": scores["milestone_points"],
            }
        )

    teams_out.sort(key=lambda t: t["total_points"], reverse=True)
    return {
        "id": event.id,
        "name": event.name,
        "wom_comp_id": event.wom_comp_id,
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "template_id": event.template_id,
        "signups_open": event.signups_open,
        "my_signup": await _my_signup(session, event.id, viewer),
        "teams": teams_out,
    }
