from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event


async def insert_feed_event(
    session: AsyncSession,
    *,
    type: str,
    player_name: str | None = None,
    data: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
    user_id: int | None = None,
    sender: str | None = None,
    is_league_world: bool = False,
    raw_message: str | None = None,
) -> None:
    """Insert an Event row into the events table, skipping silently on dedup conflict.

    Canonical shared utility for inserting feed events from any service.
    All parameters are keyword-only to prevent positional argument mistakes.
    """
    await session.execute(
        pg_insert(Event)
        .values(
            type=type,
            player_name=player_name,
            data=data or {},
            timestamp=timestamp or datetime.now(timezone.utc),
            user_id=user_id,
            sender=sender,
            is_league_world=is_league_world,
            raw_message=raw_message,
        )
        .on_conflict_do_nothing()
    )
