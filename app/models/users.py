from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from pymongo import ASCENDING


class UserProfile(BaseModel):
    """Unified user document linking Discord identity to RSN."""

    discord_user_id: int
    discord_username: str
    guild_id: int
    guild_name: str
    rsn: str | None = None
    clan_rank: str | None = None
    ticket_ids: list[int] = Field(default_factory=list)
    stats_opt_out: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


async def ensure_users_indexes(db) -> None:  # type: ignore[no-untyped-def]
    """Create indexes on the users collection. Safe to call multiple times."""
    await db["users"].create_index([("discord_user_id", ASCENDING)], unique=True)
    await db["users"].create_index([("rsn", ASCENDING)], sparse=True)
    await db["users"].create_index(
        [("guild_id", ASCENDING), ("discord_user_id", ASCENDING)]
    )
