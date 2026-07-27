from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import Leaderboard, Metric, User
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish

from ._helpers import dispatch_doc, insert_event


async def handle_level_up(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_level_up(payload.message)
    if not parsed:
        return
    data = {"skill": parsed.skill, "new_level": parsed.new_level}
    await insert_event(
        session,
        type="level",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    logger.info(
        "[{}] Level-up: {} reached {} {}",
        clan["guild_id"],
        parsed.player_name,
        parsed.skill,
        parsed.new_level,
    )
    await publish(valkey, "levelup", dispatch_doc("level", parsed.player_name, data))


async def handle_xp_milestone(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_xp_milestone(payload.message)
    if not parsed:
        return
    data = {"skill": parsed.skill, "xp": parsed.xp}
    await insert_event(
        session,
        type="xp_milestone",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    logger.info(
        "[{}] XP milestone: {} reached {:,} XP in {}",
        clan["guild_id"],
        parsed.player_name,
        parsed.xp,
        parsed.skill,
    )
    await publish(
        valkey, "xpmilestone", dispatch_doc("xp_milestone", parsed.player_name, data)
    )


async def handle_collection_log(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_collection_log(payload.message)
    if not parsed:
        return
    data = {
        "item_name": parsed.item_name,
        "log_slots": parsed.log_slots,
        "log_slots_max": parsed.log_slots_max,
    }
    await insert_event(
        session,
        type="collection_log",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    await session.execute(
        update(User)
        .where(
            func.lower(User.rsn) == parsed.player_name.lower(),
            User.collection_log_slots < parsed.log_slots,
        )
        .values(
            collection_log_slots=parsed.log_slots,
            collection_log_slots_max=parsed.log_slots_max,
            updated_at=now,
        )
    )
    await session.execute(
        pg_insert(Metric)
        .values(id="total_clogs", count=1, last_updated=now)
        .on_conflict_do_update(
            index_elements=["id"], set_={"count": Metric.count + 1, "last_updated": now}
        )
    )
    logger.info(
        "[{}] Collection log: {} - {} (slot {})",
        clan["guild_id"],
        parsed.player_name,
        parsed.item_name,
        parsed.log_slots,
    )
    await publish(
        valkey,
        "collection_log",
        dispatch_doc("collection_log", parsed.player_name, data),
    )


async def handle_personal_best(
    payload: ClanChatPayload,
    clan: dict[str, Any],
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_personal_best(payload.message)
    if not parsed:
        return
    data = {
        "activity": parsed.activity,
        "time_seconds": parsed.time_seconds,
        "variant": parsed.variant or "",
    }
    await insert_event(
        session,
        type="personal_best",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    await session.execute(
        pg_insert(Leaderboard)
        .values(
            player_name=parsed.player_name,
            activity=parsed.activity,
            variant=parsed.variant or "",
            time_seconds=parsed.time_seconds,
        )
        .on_conflict_do_update(
            index_elements=["player_name", "activity", "variant"],
            set_={
                "time_seconds": func.least(
                    Leaderboard.time_seconds, parsed.time_seconds
                )
            },
        )
    )
    logger.info(
        "[{}] PB: {} - {} in {}s",
        clan["guild_id"],
        parsed.player_name,
        parsed.activity,
        parsed.time_seconds,
    )
    await publish(
        valkey, "personal_best", dispatch_doc("personal_best", parsed.player_name, data)
    )
