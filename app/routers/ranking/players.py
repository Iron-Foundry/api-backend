from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerRanking, PlayerSnapshot, User, UserAccount
from app.dependencies import get_session
from app.services.ranking_service.scoring import rank_player_breakdown

from ._helpers import PlayerPublicSchema, get_all_deduplicated, load_ranking_config

router = APIRouter()


@router.get("/player/{rsn}", response_model=PlayerPublicSchema)
async def get_player_ranking(
    rsn: str, session: AsyncSession = Depends(get_session)
) -> PlayerPublicSchema:
    """Public ranking lookup by RSN. Returns opt-out flag so callers can redact."""
    result = await session.execute(
        select(PlayerRanking).where(PlayerRanking.rsn.ilike(rsn))
    )
    player = result.scalar_one_or_none()
    if player is None:
        raise HTTPException(404, "Player not found")

    join_date = None
    total_loot_value = None
    stats_opt_out = False

    if player.discord_user_id is not None:
        user_result = await session.execute(
            select(User.join_date, User.total_loot_value, User.stats_opt_out).where(
                User.discord_user_id == player.discord_user_id
            )
        )
        user_row = user_result.one_or_none()
        if user_row is not None:
            join_date = user_row.join_date
            total_loot_value = user_row.total_loot_value
            stats_opt_out = user_row.stats_opt_out

    return PlayerPublicSchema(
        rsn=player.rsn,
        rank=player.rank,
        points=player.points,
        boss_points=player.boss_points,
        skill_points=player.skill_points,
        join_date=join_date,
        total_loot_value=total_loot_value,
        stats_opt_out=stats_opt_out,
    )


@router.get("/results")
async def get_ranking_results(
    skip: int = 0,
    limit: int = 100,
    rank_filter: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Paginated ranked player list. Public. Use /ranking/stats for distribution data."""
    all_deduplicated = await get_all_deduplicated(session)

    deduplicated = (
        [r for r in all_deduplicated if r.rank == rank_filter]
        if rank_filter
        else all_deduplicated
    )

    total = len(deduplicated)
    page = deduplicated[skip : skip + limit]

    alt_map_result = await session.execute(
        select(UserAccount.discord_user_id, UserAccount.rsn)
    )
    alt_map: dict[int, list[str]] = defaultdict(list)
    for row in alt_map_result:
        alt_map[row.discord_user_id].append(row.rsn)

    user_ids = [r.discord_user_id for r in page if r.discord_user_id]
    username_map: dict[int, str] = {}
    clan_rank_map: dict[int, str | None] = {}
    if user_ids:
        users_result = await session.execute(
            select(User.discord_user_id, User.discord_username, User.clan_rank).where(
                User.discord_user_id.in_(user_ids)
            )
        )
        for row in users_result:
            username_map[row.discord_user_id] = row.discord_username
            clan_rank_map[row.discord_user_id] = row.clan_rank

    players = [
        {
            "rsn": r.rsn,
            "rank": r.rank,
            "points": r.points,
            "boss_points": r.boss_points,
            "skill_points": r.skill_points,
            "discord_user_id": r.discord_user_id,
            "username": username_map.get(r.discord_user_id)
            if r.discord_user_id
            else None,
            "clan_rank": clan_rank_map.get(r.discord_user_id)
            if r.discord_user_id
            else None,
            "alts": [
                a
                for a in alt_map.get(r.discord_user_id, [])
                if a.lower() != r.rsn.lower()
            ]
            if r.discord_user_id
            else [],
            "updated_at": r.updated_at.isoformat(),
        }
        for r in page
    ]

    return {"players": players, "total": total}


@router.get("/player/{rsn}/breakdown")
async def get_player_breakdown(
    rsn: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Per-metric score breakdown from cached snapshot using current config. Public."""
    snap_result = await session.execute(
        select(PlayerSnapshot).where(PlayerSnapshot.rsn.ilike(rsn))
    )
    snap = snap_result.scalar_one_or_none()
    if snap is None:
        raise HTTPException(404, "Player snapshot not found")
    config = await load_ranking_config(session)
    snapshot = {"rsn": snap.rsn, "skills": snap.skills, "bosses": snap.bosses}
    return rank_player_breakdown(snapshot, config)
