from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import FrenzyEvent, FrenzySubmission, FrenzyTeam, FrenzyTemplate
from app.dependencies import get_session, get_valkey

from ._constants import _LB_FRESH_KEY, _LB_STALE_KEY
from ._osrs_cache import _build_lb_cache
from ._scoring import _calc_item_pts, _compute_scores_from_progress

router = APIRouter()


@router.get("/leaderboards")
async def get_leaderboards(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Leaderboard data with Valkey stale-while-revalidate."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.is_active == True))
    ).scalar_one_or_none()  # noqa: E712

    metrics: list[str] = []
    wom_comp_id: int | None = None
    if event:
        metrics = event.leaderboard_metrics or []
        wom_comp_id = event.wom_comp_id

    fresh = await valkey.get(_LB_FRESH_KEY)
    if fresh:
        return {"data": json.loads(fresh), "pending_metrics": []}

    stale = await valkey.get(_LB_STALE_KEY)
    if stale:
        background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)
        return {"data": json.loads(stale), "pending_metrics": [], "stale": True}

    if metrics:
        background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)

    return {"data": [], "pending_metrics": metrics, "stale": False}


@router.get("/active/teams/{team_slug}/history")
async def get_team_history(
    team_slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Time-series of cumulative approved points for a team, plus per-player contribution."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.is_active == True))
    ).scalar_one_or_none()  # noqa: E712
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

    approved_subs = (
        (
            await session.execute(
                select(FrenzySubmission)
                .where(
                    FrenzySubmission.team_id == team.id,
                    FrenzySubmission.status == "approved",
                )
                .order_by(FrenzySubmission.submitted_at)
            )
        )
        .scalars()
        .all()
    )

    item_p: dict[str, int] = {}
    act_by_player: dict[str, dict[int, int]] = {}
    mil_by_player: dict[str, dict[int, int]] = {}
    points_series: list[dict] = []
    player_contribution: dict[str, float] = {}

    for sub in approved_subs:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_p[key] = item_p.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_by_player.setdefault(name, {})
            act_by_player[name][uid] = max(
                act_by_player[name].get(uid, 0), p.get("value", 0)
            )
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_by_player.setdefault(name, {})
            mil_by_player[name][uid] = max(
                mil_by_player[name].get(uid, 0), p.get("value", 0)
            )

        act_p = {n: sum(v.values()) for n, v in act_by_player.items()}
        mil_p = {n: sum(v.values()) for n, v in mil_by_player.items()}
        scores = _compute_scores_from_progress(template, item_p, act_p, mil_p)

        if sub.submission_type == "item":
            item_pts = 0.0
            tier_name = p.get("tier", "")
            src_name = p.get("source_name", "")
            item_name = p.get("item_name", "")
            for source in (template.tiers or {}).get(tier_name, {}).get("sources", []):
                if source.get("name") == src_name:
                    for item in source.get("items", []):
                        if item.get("name") == item_name:
                            item_pts = _calc_item_pts(item, p.get("quantity", 1))
                            break
            player_contribution[sub.player_rsn] = (
                player_contribution.get(sub.player_rsn, 0.0) + item_pts
            )

        points_series.append(
            {
                "timestamp": sub.submitted_at.isoformat(),
                "total_points": scores["total"],
                "player_rsn": sub.player_rsn,
                "submission_type": sub.submission_type,
                "payload": sub.payload,
            }
        )

    return {
        "team_slug": team_slug,
        "series": points_series,
        "player_contribution": player_contribution,
    }


@router.get("/active/history")
async def get_event_history(session: AsyncSession = Depends(get_session)) -> dict:
    """All teams' cumulative points over time - used for rank-over-time chart."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.is_active == True))
    ).scalar_one_or_none()  # noqa: E712
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    teams = (
        (
            await session.execute(
                select(FrenzyTeam).where(FrenzyTeam.event_id == event.id)
            )
        )
        .scalars()
        .all()
    )
    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one()

    all_subs = (
        (
            await session.execute(
                select(FrenzySubmission)
                .where(
                    FrenzySubmission.event_id == event.id,
                    FrenzySubmission.status == "approved",
                )
                .order_by(FrenzySubmission.submitted_at)
            )
        )
        .scalars()
        .all()
    )

    item_states: dict[int, dict[str, int]] = {t.id: {} for t in teams}
    act_states: dict[int, dict[str, dict[int, int]]] = {t.id: {} for t in teams}
    mil_states: dict[int, dict[str, dict[int, int]]] = {t.id: {} for t in teams}
    team_series: dict[int, list[dict]] = {t.id: [] for t in teams}

    for sub in all_subs:
        tid = sub.team_id
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_states[tid][key] = item_states[tid].get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_states[tid].setdefault(name, {})
            act_states[tid][name][uid] = max(
                act_states[tid][name].get(uid, 0), p.get("value", 0)
            )
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_states[tid].setdefault(name, {})
            mil_states[tid][name][uid] = max(
                mil_states[tid][name].get(uid, 0), p.get("value", 0)
            )

        act_p = {n: sum(v.values()) for n, v in act_states[tid].items()}
        mil_p = {n: sum(v.values()) for n, v in mil_states[tid].items()}
        scores = _compute_scores_from_progress(template, item_states[tid], act_p, mil_p)
        team_series[tid].append(
            {"timestamp": sub.submitted_at.isoformat(), "total_points": scores["total"]}
        )

    return {
        "teams": [
            {"id": t.id, "name": t.name, "slug": t.slug, "series": team_series[t.id]}
            for t in teams
        ]
    }
