from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish

from ._helpers import dispatch_doc, increment_loot_value, insert_event


async def handle_loot(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_loot(payload.message)
    if not parsed:
        return
    data = {
        "item_name": parsed.item_name,
        "coin_value": parsed.coin_value,
        "source": parsed.source,
        "rank": payload.rank,
        "sender": payload.sender,
    }
    await insert_event(
        session,
        type="loot",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    if parsed.coin_value is not None:
        await increment_loot_value(session, parsed.player_name, parsed.coin_value)
    logger.info(
        "[{}] Loot: {} got {} ({}gp)",
        clan["guild_id"],
        parsed.player_name,
        parsed.item_name,
        parsed.coin_value,
    )
    await publish(valkey, "loot", dispatch_doc("loot", parsed.player_name, data))


async def handle_loot_key(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_loot_key(payload.message)
    if not parsed:
        return
    data = {"coin_value": parsed.coin_value}
    await insert_event(
        session,
        type="loot_key",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    await increment_loot_value(session, parsed.player_name, parsed.coin_value)
    logger.info(
        "[{}] Loot key: {} opened key worth {:,}gp",
        clan["guild_id"],
        parsed.player_name,
        parsed.coin_value,
    )
    await publish(
        valkey, "loot_key", dispatch_doc("loot_key", parsed.player_name, data)
    )


async def handle_clue_item(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_clue_item(payload.message)
    if not parsed:
        return
    data = {"item_name": parsed.item_name, "coin_value": parsed.coin_value}
    await insert_event(
        session,
        type="clue_item",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    if parsed.coin_value is not None:
        await increment_loot_value(session, parsed.player_name, parsed.coin_value)
    logger.info(
        "[{}] Clue item: {} got {}",
        clan["guild_id"],
        parsed.player_name,
        parsed.item_name,
    )
    await publish(
        valkey, "clue_item", dispatch_doc("clue_item", parsed.player_name, data)
    )
