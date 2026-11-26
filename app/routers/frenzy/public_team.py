"""The public detail of one team in the running frenzy event."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzySubmission, FrenzyTeam, FrenzyTemplate
from app.dependencies import get_session

from ._scoring import (
    _apply_pending_submissions,
    _calc_item_pts,
    _compute_scores_from_progress,
    _compute_team_scores,
)

router = APIRouter()


@router.get("/active/teams/{team_slug}")
async def get_active_team_detail(
    team_slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Full team detail: template merged with team progress and computed scores."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event.id, FrenzyTeam.slug == team_slug
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one()
    scores = _compute_team_scores(template, team)

    pending_subs = (
        (
            await session.execute(
                select(FrenzySubmission).where(
                    FrenzySubmission.team_id == team.id,
                    FrenzySubmission.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )

    if pending_subs:
        pi, pa, pm = _apply_pending_submissions(
            team.item_progress or {},
            team.activity_progress or {},
            team.milestone_progress or {},
            pending_subs,
        )
        pending_points = (
            _compute_scores_from_progress(template, pi, pa, pm)["total"]
            - scores["total"]
        )
    else:
        pending_points = 0.0

    approved_subs = (
        (
            await session.execute(
                select(FrenzySubmission).where(
                    FrenzySubmission.team_id == team.id,
                    FrenzySubmission.status == "approved",
                )
            )
        )
        .scalars()
        .all()
    )

    player_contribution: dict[str, float] = {}
    for sub in approved_subs:
        if sub.submission_type != "item":
            continue
        p = sub.payload or {}
        tier_name = p.get("tier", "")
        src_name = p.get("source_name", "")
        item_name = p.get("item_name", "")
        pts = 0.0
        for source in (template.tiers or {}).get(tier_name, {}).get("sources", []):
            if source.get("name") == src_name:
                for item in source.get("items", []):
                    if item.get("name") == item_name:
                        pts = _calc_item_pts(item, p.get("quantity", 1))
                        break
        player_contribution[sub.player_rsn] = (
            player_contribution.get(sub.player_rsn, 0.0) + pts
        )

    return {
        "id": team.id,
        "name": team.name,
        "slug": team.slug,
        "icon_url": team.icon_url,
        "participants": team.participants or [],
        "template": {
            "tiers": template.tiers,
            "activities": template.activities,
            "milestones": template.milestones,
            "multipliers": template.multipliers,
        },
        "progress": {
            "item_progress": team.item_progress,
            "activity_progress": team.activity_progress,
            "milestone_progress": team.milestone_progress,
        },
        "scores": scores,
        "pending_points": pending_points,
        "player_contribution": player_contribution,
    }
