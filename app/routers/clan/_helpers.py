from __future__ import annotations

from typing import Any, Never

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, User, UserAccount, WomClanRank

from ._constants import (
    _COMP_METRIC_FINISHED_FRESH_TTL,
    _COMP_METRIC_ONGOING_FRESH_TTL,
    _COMP_METRIC_UPCOMING_FRESH_TTL,
    _GLOBAL_GUILD_ID,
)


def _comp_metric_keys(comp_id: int, metric: str) -> tuple[str, str, str]:
    base = f"clan:comp:{comp_id}:metric:{metric}"
    return f"{base}:fresh", f"{base}:stale", f"{base}:lock"


def _comp_metric_fresh_ttl(status: str) -> int:
    if status == "ongoing":
        return _COMP_METRIC_ONGOING_FRESH_TTL
    if status == "upcoming":
        return _COMP_METRIC_UPCOMING_FRESH_TTL
    return _COMP_METRIC_FINISHED_FRESH_TTL


def _handle_wom_error(exc: httpx.HTTPStatusError) -> Never:
    status = exc.response.status_code
    try:
        detail = exc.response.json().get("message", str(exc))
    except Exception:
        detail = str(exc)
    if status == 400:
        raise HTTPException(400, f"WOM rejected request: {detail}")
    if status == 404:
        raise HTTPException(404, "Competition not found on WOM.")
    if status == 429:
        raise HTTPException(429, "WOM rate limit reached.")
    raise HTTPException(502, f"WOM upstream error: {detail}")


async def _enrich_with_ranks(
    entries_by_name: dict[str, list[dict[str, Any]]],
    session: AsyncSession,
) -> None:
    """Mutate entry dicts in-place, adding clan_rank and discord_rank."""
    names = list(entries_by_name.keys())
    if not names:
        return

    cfg_result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID, Config.key == "clan_rank_mappings"
        )
    )
    cfg = cfg_result.scalar_one_or_none() or {}
    role_id_to_rank: dict[str, tuple[int, str]] = {
        m["discord_role_id"]: (m.get("order", 0), m.get("label", ""))
        for m in cfg.get("mappings", [])
        if m.get("discord_role_id") and m.get("label")
    }

    def _highest_discord_rank(discord_roles: list[str]) -> str | None:
        best_order, best_label = -1, None
        for rid in discord_roles:
            if rid in role_id_to_rank:
                order, label = role_id_to_rank[rid]
                if order > best_order:
                    best_order, best_label = order, label
        return best_label

    rank_map: dict[str, tuple[str | None, str | None]] = {}
    uid_map: dict[str, int | None] = {}
    ua_rows = await session.execute(
        select(
            func.lower(UserAccount.rsn),
            User.clan_rank,
            User.discord_roles,
            UserAccount.is_primary,
            UserAccount.discord_user_id,
        )
        .join(User, User.discord_user_id == UserAccount.discord_user_id)
        .where(func.lower(UserAccount.rsn).in_(names))
    )
    for rsn, clan_rank, discord_roles, is_primary, discord_user_id in ua_rows:
        dr = _highest_discord_rank(discord_roles or []) if is_primary else None
        rank_map[rsn] = (clan_rank, dr)
        uid_map[rsn] = discord_user_id

    legacy_rows = await session.execute(
        select(
            func.lower(User.rsn),
            User.clan_rank,
            User.discord_roles,
            User.discord_user_id,
        ).where(func.lower(User.rsn).in_(names), User.rsn.isnot(None))
    )
    for rsn, clan_rank, discord_roles, discord_user_id in legacy_rows:
        if rsn not in rank_map:
            rank_map[rsn] = (clan_rank, _highest_discord_rank(discord_roles or []))
        if rsn not in uid_map:
            uid_map[rsn] = discord_user_id

    wom_missing = [name for name in entries_by_name if name not in rank_map]
    if wom_missing:
        wom_rows = await session.execute(
            select(WomClanRank.rsn, WomClanRank.clan_rank).where(
                WomClanRank.rsn.in_(wom_missing)
            )
        )
        for rsn, clan_rank in wom_rows:
            rank_map[rsn] = (clan_rank, None)

    for name, entry_list in entries_by_name.items():
        clan_rank, discord_rank = rank_map.get(name, (None, None))
        uid = uid_map.get(name)
        for e in entry_list:
            e["clan_rank"] = clan_rank
            e["discord_rank"] = discord_rank
            e["_discord_user_id"] = uid
