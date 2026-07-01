from __future__ import annotations

from datetime import datetime

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, PlayerRanking
from app.services.ranking_service.config import (
    _DEFAULT_CONFIG,
    _GLOBAL_GUILD_ID,
    _RANKING_CONFIG_KEY,
)
from app.services.ranking_service.scoring import RankingConfig


class PlayerPublicSchema(BaseModel):
    rsn: str
    rank: str
    points: int
    boss_points: int
    skill_points: int
    join_date: datetime | None
    total_loot_value: int | None
    stats_opt_out: bool


RANK_ORDER: dict[str, int] = {"No Rank": 0, **{f"Rank {i}": i for i in range(1, 11)}}

INGAME_TO_DISPLAY: dict[str, str] = {
    "guest": "Guest",
    "achiever": "Achiever",
    "sapphire": "Sapphire",
    "emerald": "Emerald",
    "ruby": "Ruby",
    "diamond": "Diamond",
    "dragonstone": "Dragonstone",
    "onyx": "Onyx",
    "zenyte": "Zenyte",
}


async def get_all_deduplicated(session: AsyncSession) -> list[PlayerRanking]:
    rows = (await session.execute(select(PlayerRanking))).scalars().all()
    best_per_user: dict[int, PlayerRanking] = {}
    unlinked: list[PlayerRanking] = []
    for r in rows:
        if r.discord_user_id is None:
            unlinked.append(r)
        else:
            prev = best_per_user.get(r.discord_user_id)
            if prev is None or r.points > prev.points:
                best_per_user[r.discord_user_id] = r
    result = list(best_per_user.values()) + unlinked
    result.sort(key=lambda r: (-RANK_ORDER.get(r.rank, 0), -r.points))
    return result


async def load_ranking_config(session: AsyncSession) -> RankingConfig:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _RANKING_CONFIG_KEY,
        )
    )
    stored = result.scalar_one_or_none()
    if not stored or stored.get("version") != 2:
        return _DEFAULT_CONFIG
    try:
        return RankingConfig.from_dict(stored)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("load_ranking_config parse error: {} - using defaults", exc)
        return _DEFAULT_CONFIG


def compute_breakdown(players: list[dict]) -> dict:
    rank_dist: dict[str, int] = {r: 0 for r in RANK_ORDER}
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
