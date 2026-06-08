from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, User
from app.dependencies import get_current_user, get_session

from ._helpers import INGAME_TO_DISPLAY, compute_breakdown, get_all_deduplicated

router = APIRouter()


@router.get("/status")
async def get_ranking_status(
    request: Request,
    _: dict = Depends(get_current_user),
) -> dict:
    """Last run info. All authenticated users."""
    svc = getattr(request.app.state, "ranking_service", None)
    if svc is None:
        return {
            "last_run_at": None,
            "player_count": 0,
            "last_error": None,
            "service_active": False,
            "is_running": False,
        }
    return {
        "last_run_at": svc.last_run_at.isoformat() if svc.last_run_at else None,
        "player_count": svc.last_run_count,
        "last_error": svc.last_error,
        "service_active": True,
        "is_running": svc.run_active,
    }


@router.get("/stats")
async def get_ranking_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Full WOM + clan rank distribution across all ranked players. Public."""
    all_deduplicated = await get_all_deduplicated(session)

    breakdown = compute_breakdown(
        [{"rank": r.rank, "boss_points": r.boss_points, "skill_points": r.skill_points}
         for r in all_deduplicated]
    )

    user_ids = [r.discord_user_id for r in all_deduplicated if r.discord_user_id]
    clan_rank_dist: dict[str, int] = {}
    rank_overlap: dict[str, dict[str, int]] = {}
    if user_ids:
        cfg_result = await session.execute(
            select(Config.value).where(Config.guild_id == 0, Config.key == "clan_rank_mappings")
        )
        cfg = cfg_result.scalar_one_or_none() or {}
        role_id_to_rank: dict[str, tuple[int, str]] = {
            m["discord_role_id"]: (m.get("order", 0), m.get("label", ""))
            for m in cfg.get("mappings", [])
            if m.get("discord_role_id") and m.get("label")
        }

        def _highest_discord_rank(discord_roles: list) -> str | None:
            best_order, best_label = -1, None
            for rid in discord_roles:
                if rid in role_id_to_rank:
                    order, label = role_id_to_rank[rid]
                    if order > best_order:
                        best_order, best_label = order, label
            return best_label

        user_rows = await session.execute(
            select(User.discord_user_id, User.clan_rank, User.discord_roles).where(
                User.discord_user_id.in_(user_ids)
            )
        )
        user_data_by_id: dict[int, tuple[str | None, list]] = {
            row.discord_user_id: (row.clan_rank, row.discord_roles or [])
            for row in user_rows
        }
        for r in all_deduplicated:
            if not r.discord_user_id:
                continue
            clan_rank_raw, discord_roles = user_data_by_id.get(r.discord_user_id, (None, []))
            display_rank = _highest_discord_rank(discord_roles) or (
                INGAME_TO_DISPLAY.get(clan_rank_raw, clan_rank_raw) if clan_rank_raw else None
            )
            if display_rank:
                clan_rank_dist[display_rank] = clan_rank_dist.get(display_rank, 0) + 1
                wom_bucket = rank_overlap.setdefault(r.rank, {})
                wom_bucket[display_rank] = wom_bucket.get(display_rank, 0) + 1

    return {
        "total": len(all_deduplicated),
        "rank_distribution": breakdown["rank_distribution"],
        "clan_rank_distribution": clan_rank_dist,
        "rank_overlap": rank_overlap,
        "avg_boss_pct": breakdown["avg_boss_pct"],
        "avg_skill_pct": breakdown["avg_skill_pct"],
    }
