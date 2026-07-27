from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerRanking
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import RANK_ORDER, compute_breakdown

router = APIRouter()


@router.post(
    "/run",
    dependencies=[Depends(require_page_permission("staff.ranking", "create"))],
)
async def trigger_ranking_run(request: Request) -> dict[str, Any]:
    """Trigger an immediate ranking run. Staff only."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        raise HTTPException(
            503, "Ranking service not running (WOM_GROUP_ID not configured)"
        )
    if not svc.run_now():
        raise HTTPException(409, "Ranking run already in progress")
    return {"status": "triggered"}


@router.post(
    "/preview",
    dependencies=[Depends(require_page_permission("staff.ranking", "read"))],
)
async def preview_ranking(
    body: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Re-rank from cached snapshots using a trial config. No DB writes."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        raise HTTPException(
            503, "Ranking service not running (WOM_GROUP_ID not configured)"
        )

    preview_ranked = await svc.rank_from_config(body)

    current_result = await session.execute(
        select(PlayerRanking.rsn, PlayerRanking.rank, PlayerRanking.points)
    )
    current_map: dict[str, dict[str, Any]] = {
        row.rsn: {"rank": row.rank, "points": row.points} for row in current_result
    }

    promotions = demotions = unchanged = 0
    players = []
    for p in preview_ranked:
        cur = current_map.get(p["rsn"])
        cur_rank = cur["rank"] if cur else None
        cur_points = cur["points"] if cur else None

        rank_changed = cur_rank != p["rank"]
        if rank_changed and cur_rank is not None:
            if RANK_ORDER.get(p["rank"], 0) > RANK_ORDER.get(cur_rank, 0):
                promotions += 1
            else:
                demotions += 1
        else:
            unchanged += 1

        players.append(
            {
                "rsn": p["rsn"],
                "current_rank": cur_rank,
                "current_points": cur_points,
                "preview_rank": p["rank"],
                "preview_points": p["points"],
                "boss_points": p["boss_points"],
                "skill_points": p["skill_points"],
                "rank_changed": rank_changed,
                "points_delta": p["points"] - cur_points
                if cur_points is not None
                else None,
            }
        )

    players.sort(
        key=lambda x: (
            0 if x["rank_changed"] else 1,
            -abs(
                RANK_ORDER.get(x["preview_rank"], 0)
                - RANK_ORDER.get(x["current_rank"] or "No Rank", 0)
            ),
            -(x["points_delta"] or 0),
        )
    )

    breakdown = compute_breakdown(
        [
            {
                "rank": p["preview_rank"],
                "boss_points": p["boss_points"],
                "skill_points": p["skill_points"],
            }
            for p in players
        ]
    )
    breakdown["promotions"] = promotions
    breakdown["demotions"] = demotions
    breakdown["unchanged"] = unchanged

    return {"players": players, "breakdown": breakdown}
