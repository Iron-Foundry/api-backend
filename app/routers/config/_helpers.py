from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config

_GLOBAL_GUILD_ID = 0
_DISCORD_GUILD_ID = int(os.getenv("GUILD_ID", "0"))

_RANK_MAPPINGS_KEY = "clan_rank_mappings"
_PAGE_PERMISSIONS_KEY = "page_permissions"
_ADMIN_BYPASS_KEY = "admin_bypass_roles"
_NOTIFICATION_CATEGORIES_KEY = "party_notification_categories"
_RANKING_CONFIG_KEY = "ranking_config"
_DISCORD_ROLES_KEY = "discord_roles"
_SERVICE_TOGGLES_KEY = "service_toggles"
_TICKET_FEATURES_KEY = "ticket_features"
_PANEL_CONFIG_KEY = "info_panel_config"
_BALLOT_TOKEN_CONFIG_KEY = "ballot_token_config"

_ALL_SERVICE_KEYS: list[str] = [
    "wom_name_change",
    "clan_stats",
    "ranking",
    "competition_snapshot",
    "competition_schedule",
    "metric_compaction",
    "discord_chat",
    "music_state",
    "music_stats",
    "party_expiry",
    "efficiency_rates",
    "loot_tables",
]


async def get_config_value(key: str, session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID, Config.key == key
        )
    )
    return result.scalar_one_or_none() or {}


async def set_config_value(
    key: str, value: dict[str, Any], session: AsyncSession
) -> None:
    await session.execute(
        pg_insert(Config)
        .values(guild_id=_GLOBAL_GUILD_ID, key=key, value=value)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"], set_={"value": value}
        )
    )
    await session.commit()


async def get_guild_config_value(key: str, session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _DISCORD_GUILD_ID, Config.key == key
        )
    )
    return result.scalar_one_or_none() or {}


async def set_guild_config_value(
    key: str, value: dict[str, Any], session: AsyncSession
) -> None:
    await session.execute(
        pg_insert(Config)
        .values(guild_id=_DISCORD_GUILD_ID, key=key, value=value)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"], set_={"value": value}
        )
    )
    await session.commit()


async def get_service_toggles(session: AsyncSession) -> dict[str, bool]:
    """Return service toggle states, defaulting to True for any unset key."""
    data = await get_config_value(_SERVICE_TOGGLES_KEY, session)
    defaults: dict[str, bool] = dict.fromkeys(_ALL_SERVICE_KEYS, True)
    defaults.update({k: bool(v) for k, v in data.items() if k in defaults})
    return defaults
