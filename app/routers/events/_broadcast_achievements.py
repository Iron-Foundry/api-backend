from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish

from ._helpers import dispatch_doc, insert_event


async def handle_achievement(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_achievement(payload.message)
    if not parsed:
        return
    data: dict[str, Any] = {"achievement_type": parsed.kind, "name": parsed.name}
    if parsed.difficulty:
        data["difficulty"] = parsed.difficulty
    await insert_event(
        session,
        type=parsed.kind,
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    logger.info(
        "[{}] Achievement: {} - {}", clan["guild_id"], parsed.player_name, parsed.name
    )
    await publish(
        valkey, "achievement", dispatch_doc(parsed.kind, parsed.player_name, data)
    )


async def handle_pet(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_pet(payload.message)
    if not parsed:
        return
    await insert_event(
        session,
        type="pet",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data={},
    )
    logger.info("[{}] Pet drop: {}", clan["guild_id"], parsed.player_name)
    await publish(valkey, "pet", dispatch_doc("pet", parsed.player_name, {}))
