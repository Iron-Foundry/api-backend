"""Shared utility: compute a user's effective roles (Discord roles + rank-mapped roles)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, User

_GLOBAL_GUILD_ID = 0
_RANK_MAPPINGS_KEY = "clan_rank_mappings"


async def get_role_label_map(session: AsyncSession) -> dict[str, str]:
    """Return {discord_role_id: label} from clan_rank_mappings config."""
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _RANK_MAPPINGS_KEY,
        )
    )
    cfg = result.scalar_one_or_none() or {}
    return {
        m["discord_role_id"]: m.get("label", "")
        for m in cfg.get("mappings", [])
        if "discord_role_id" in m
    }


async def get_effective_roles(discord_user_id: int, session: AsyncSession) -> list[str]:
    """Return the user's effective Discord roles.

    Merges their stored ``discord_roles`` with any additional roles derived
    from their ``clan_rank`` via the clan-rank-mappings config.
    """
    user_result = await session.execute(
        select(User.discord_roles, User.clan_rank).where(
            User.discord_user_id == discord_user_id
        )
    )
    row = user_result.one_or_none()
    discord_roles: list[str] = (row.discord_roles if row else None) or []
    clan_rank: str | None = row.clan_rank if row else None

    cfg_result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _RANK_MAPPINGS_KEY,
        )
    )
    cfg = cfg_result.scalar_one_or_none() or {}
    mappings: list[dict[str, Any]] = cfg.get("mappings", [])

    # Support both new (discord_role_id) and legacy (discord_role) field names
    mapped: list[str] = [
        m.get("discord_role_id") or m.get("discord_role", "")
        for m in mappings
        if m.get("clan_rank") == clan_rank
        and (m.get("discord_role_id") or m.get("discord_role"))
    ]

    seen: set[str] = set()
    effective: list[str] = []
    for role in discord_roles + mapped:
        if role not in seen:
            seen.add(role)
            effective.append(role)
    return effective
