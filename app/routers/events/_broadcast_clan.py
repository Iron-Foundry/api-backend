from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import CofferEvent, MembershipEvent
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish

from ._helpers import dispatch_doc, insert_event


async def handle_new_member(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_new_member(payload.message)
    if not parsed:
        return
    data = {"invited_by": parsed.invited_by}
    await insert_event(
        session,
        type="new_member",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data=data,
    )
    logger.info(
        "[{}] New member: {} (invited by {})",
        clan["guild_id"],
        parsed.player_name,
        parsed.invited_by,
    )
    await publish(
        valkey, "new_member", dispatch_doc("new_member", parsed.player_name, data)
    )


async def handle_clan_leave(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_clan_leave(payload.message)
    if not parsed:
        return
    session.add(
        MembershipEvent(
            timestamp=now,
            player_name=parsed.player_name,
            sender=payload.sender,
            is_league_world=payload.is_league_world,
            raw_message=payload.message,
            expelled_by=parsed.expelled_by,
        )
    )
    if parsed.expelled_by:
        logger.info(
            "[{}] Expelled: {} by {}",
            clan["guild_id"],
            parsed.player_name,
            parsed.expelled_by,
        )
        await publish(
            valkey,
            "expelled",
            dispatch_doc(
                "expelled", parsed.player_name, {"expelled_by": parsed.expelled_by}
            ),
        )
    else:
        logger.info("[{}] Left clan: {}", clan["guild_id"], parsed.player_name)
        await publish(
            valkey, "left_clan", dispatch_doc("left_clan", parsed.player_name, {})
        )


async def handle_coffer(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_coffer_transaction(payload.message)
    if not parsed:
        return
    session.add(
        CofferEvent(
            timestamp=now,
            player_name=parsed.player_name,
            sender=payload.sender,
            is_league_world=payload.is_league_world,
            raw_message=payload.message,
            amount=parsed.amount,
            is_donation=parsed.is_donation,
        )
    )
    logger.info(
        "[{}] Coffer {}: {} {:,}gp",
        clan["guild_id"],
        "deposit" if parsed.is_donation else "withdrawal",
        parsed.player_name,
        parsed.amount,
    )
    event_type = "coffer_donation" if parsed.is_donation else "coffer_withdrawal"
    await publish(
        valkey,
        event_type,
        dispatch_doc(
            event_type,
            parsed.player_name,
            {"amount": parsed.amount, "is_donation": parsed.is_donation},
        ),
    )


async def handle_hcim_death(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
    now: datetime,
) -> None:
    parsed = parser.parse_hcim_death(payload.message)
    if not parsed:
        return
    await insert_event(
        session,
        type="hcim_death",
        timestamp=now,
        player_name=parsed.player_name,
        sender=payload.sender,
        is_league_world=payload.is_league_world,
        raw_message=payload.message,
        data={},
    )
    logger.info("[{}] HCIM death: {}", clan["guild_id"], parsed.player_name)
    await publish(
        valkey, "hcim_death", dispatch_doc("hcim_death", parsed.player_name, {})
    )
