"""Ranking router - clan member ranking results and config preview."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collections import defaultdict

from app.db.models import PlayerRanking, User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission
from app.services.ranking_service import _DEFAULT_CONFIG

router = APIRouter(prefix="/ranking", tags=["ranking"])

_RANK_ORDER = {"No Rank": 0, "Rank 1": 1, "Rank 2": 2, "Rank 3": 3, "Rank 4": 4, "Rank 5": 5, "Rank 6": 6}


def _compute_breakdown(players: list[dict]) -> dict:
    if not players:
        return {
            "avg_boss_pct": 0.0,
            "avg_skill_pct": 0.0,
            "rank_distribution": {},
        }

    rank_dist: dict[str, int] = {}
    boss_pcts: list[float] = []

    for p in players:
        rank_dist[p["rank"]] = rank_dist.get(p["rank"], 0) + 1
        total = p["boss_points"] + p["skill_points"]
        if total > 0:
            boss_pcts.append(p["boss_points"] / total * 100)

    avg_boss = sum(boss_pcts) / len(boss_pcts) if boss_pcts else 0.0
    return {
        "avg_boss_pct": round(avg_boss, 1),
        "avg_skill_pct": round(100 - avg_boss, 1),
        "rank_distribution": rank_dist,
    }


@router.get("/status")
async def get_ranking_status(
    request: Request,
    _: dict = Depends(get_current_user),
) -> dict:
    """Last run info. All authenticated users."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        return {"last_run_at": None, "player_count": 0, "last_error": None, "service_active": False, "is_running": False}
    return {
        "last_run_at": svc.last_run_at.isoformat() if svc.last_run_at else None,
        "player_count": svc.last_run_count,
        "last_error": svc.last_error,
        "service_active": True,
        "is_running": svc.is_running,
    }


@router.get("/results")
async def get_ranking_results(
    skip: int = 0,
    limit: int = 100,
    rank_filter: str | None = None,
    _: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Paginated ranked player list. All authenticated users.

    For users with multiple linked RSNs, only the highest-scoring alt is shown
    (best alt wins).
    """
    stmt = select(PlayerRanking)
    if rank_filter:
        stmt = stmt.where(PlayerRanking.rank == rank_filter)

    all_rows = await session.execute(stmt)
    all_rankings = all_rows.scalars().all()

    # Deduplicate: keep best-scoring entry per discord_user_id
    best_per_user: dict[int, PlayerRanking] = {}
    unlinked: list[PlayerRanking] = []
    for r in all_rankings:
        if r.discord_user_id is None:
            unlinked.append(r)
        else:
            prev = best_per_user.get(r.discord_user_id)
            if prev is None or r.points > prev.points:
                best_per_user[r.discord_user_id] = r

    deduplicated = list(best_per_user.values()) + unlinked

    # Apply rank filter to deduplicated list (already filtered by stmt, but unlinked rows
    # with wrong rank could slip through if no filter - stmt handles this)

    # Sort by rank order then points descending
    deduplicated.sort(
        key=lambda r: (-_RANK_ORDER.get(r.rank, 0), -r.points)
    )

    total = len(deduplicated)
    page = deduplicated[skip : skip + limit]

    # Build alt map from user_accounts
    alt_map_result = await session.execute(
        select(UserAccount.discord_user_id, UserAccount.rsn)
    )
    alt_map: dict[int, list[str]] = defaultdict(list)
    for row in alt_map_result:
        alt_map[row.discord_user_id].append(row.rsn)

    # Fetch linked usernames
    user_ids = [r.discord_user_id for r in page if r.discord_user_id]
    username_map: dict[int, str] = {}
    if user_ids:
        users_result = await session.execute(
            select(User.discord_user_id, User.discord_username).where(
                User.discord_user_id.in_(user_ids)
            )
        )
        username_map = {row.discord_user_id: row.discord_username for row in users_result}

    players = [
        {
            "rsn": r.rsn,
            "rank": r.rank,
            "points": r.points,
            "boss_points": r.boss_points,
            "skill_points": r.skill_points,
            "discord_user_id": r.discord_user_id,
            "username": username_map.get(r.discord_user_id) if r.discord_user_id else None,
            "alts": [a for a in alt_map.get(r.discord_user_id, []) if a.lower() != r.rsn.lower()]
            if r.discord_user_id
            else [],
            "updated_at": r.updated_at.isoformat(),
        }
        for r in page
    ]

    return {
        "players": players,
        "total": total,
        "breakdown": _compute_breakdown(players),
    }


@router.post(
    "/run",
    dependencies=[Depends(require_page_permission("staff.ranking", "create"))],
)
async def trigger_ranking_run(request: Request) -> dict:
    """Trigger an immediate ranking run. Staff only."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        raise HTTPException(503, "Ranking service not running (WOM_GROUP_ID not configured)")
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
) -> dict:
    """Re-rank from cached snapshots using a trial config. No DB writes."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        raise HTTPException(503, "Ranking service not running (WOM_GROUP_ID not configured)")

    # Merge provided config over defaults so partial bodies work
    config = dict(_DEFAULT_CONFIG)
    config.update(body)

    preview_ranked = await svc.rank_from_config(config)

    # Fetch current rankings for diff
    current_result = await session.execute(
        select(PlayerRanking.rsn, PlayerRanking.rank, PlayerRanking.points)
    )
    current_map: dict[str, dict] = {
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
            if _RANK_ORDER.get(p["rank"], 0) > _RANK_ORDER.get(cur_rank, 0):
                promotions += 1
            else:
                demotions += 1
        else:
            unchanged += 1

        players.append({
            "rsn": p["rsn"],
            "current_rank": cur_rank,
            "current_points": cur_points,
            "preview_rank": p["rank"],
            "preview_points": p["points"],
            "boss_points": p["boss_points"],
            "skill_points": p["skill_points"],
            "rank_changed": rank_changed,
            "points_delta": p["points"] - cur_points if cur_points is not None else None,
        })

    # Sort: rank changes first (by magnitude), then by points_delta
    players.sort(key=lambda x: (
        0 if x["rank_changed"] else 1,
        -abs(_RANK_ORDER.get(x["preview_rank"], 0) - _RANK_ORDER.get(x["current_rank"] or "No Rank", 0)),
        -(x["points_delta"] or 0),
    ))

    breakdown = _compute_breakdown([
        {"rank": p["preview_rank"], "boss_points": p["boss_points"], "skill_points": p["skill_points"]}
        for p in players
    ])
    breakdown["promotions"] = promotions
    breakdown["demotions"] = demotions
    breakdown["unchanged"] = unchanged

    return {"players": players, "breakdown": breakdown}
