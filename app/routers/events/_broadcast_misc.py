from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish

from ._helpers import dispatch_doc, insert_event


async def handle_pk(payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey, now: datetime) -> None:
    parsed = parser.parse_pk(payload.message)
    if not parsed:
        return
    data = {"winner": parsed.winner, "loser": parsed.loser, "gp_exchanged": parsed.gp_exchanged}
    await insert_event(session, type="pk", timestamp=now, player_name=parsed.winner, sender=payload.sender, is_league_world=payload.is_league_world, raw_message=payload.message, data=data)
    logger.info("[{}] PK: {} defeated {} ({} gp)", clan["guild_id"], parsed.winner, parsed.loser, parsed.gp_exchanged)
    await publish(valkey, "pk", dispatch_doc("pk", parsed.winner, data))


async def handle_league_relic(payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey, now: datetime) -> None:
    parsed = parser.parse_league_relic(payload.message)
    if not parsed:
        return
    data = {"tier": parsed.tier}
    await insert_event(session, type="league_relic", timestamp=now, player_name=parsed.player_name, sender=payload.sender, is_league_world=payload.is_league_world, raw_message=payload.message, data=data)
    logger.info("[{}] League relic: {} unlocked tier {}", clan["guild_id"], parsed.player_name, parsed.tier)
    await publish(valkey, "league_relic", dispatch_doc("league_relic", parsed.player_name, data))


async def handle_league_rank(payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey, now: datetime) -> None:
    parsed = parser.parse_league_rank(payload.message)
    if not parsed:
        return
    data = {"rank": parsed.rank}
    await insert_event(session, type="league_rank", timestamp=now, player_name=parsed.player_name, sender=payload.sender, is_league_world=payload.is_league_world, raw_message=payload.message, data=data)
    logger.info("[{}] League rank: {} earned {}", clan["guild_id"], parsed.player_name, parsed.rank)
    await publish(valkey, "league_rank", dispatch_doc("league_rank", parsed.player_name, data))


async def handle_league_area(payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey, now: datetime) -> None:
    parsed = parser.parse_league_area(payload.message)
    if not parsed:
        return
    data = {"area_count": parsed.area_count}
    await insert_event(session, type="league_area", timestamp=now, player_name=parsed.player_name, sender=payload.sender, is_league_world=payload.is_league_world, raw_message=payload.message, data=data)
    logger.info("[{}] League area: {} unlocked area {}", clan["guild_id"], parsed.player_name, parsed.area_count if parsed.area_count is not None else "final")
    await publish(valkey, "league_area", dispatch_doc("league_area", parsed.player_name, data))


async def handle_unknown(payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey, now: datetime) -> None:
    await insert_event(session, type="unknown", timestamp=now, sender=payload.sender, is_league_world=payload.is_league_world, raw_message=payload.message, data={})
    await publish(valkey, "unknown", dispatch_doc("unknown", None, {"raw_message": payload.message}))
    logger.debug("[{}] Unknown broadcast: {}", clan["guild_id"], payload.message)
