from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import CofferEvent, Event, Leaderboard, MembershipEvent, User
from app.dependencies import get_session, get_valkey, verify_clan
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import is_duplicate, publish
from app.services.parser import BroadcastType

router = APIRouter(tags=["clan"])

# Maps broadcast types that carry a single player_name to their parser.
_PLAYER_NAME_PARSERS: dict[BroadcastType, Callable[[str], Any]] = {
    BroadcastType.LOOT: parser.parse_loot,
    BroadcastType.LEVEL_UP: parser.parse_level_up,
    BroadcastType.XP_MILESTONE: parser.parse_xp_milestone,
    BroadcastType.QUEST: parser.parse_achievement,
    BroadcastType.DIARY: parser.parse_achievement,
    BroadcastType.COMBAT_ACHIEVEMENT: parser.parse_achievement,
    BroadcastType.PET: parser.parse_pet,
    BroadcastType.NEW_MEMBER: parser.parse_new_member,
    BroadcastType.COLLECTION_LOG: parser.parse_collection_log,
    BroadcastType.LOOT_KEY: parser.parse_loot_key,
    BroadcastType.CLUE_ITEM: parser.parse_clue_item,
    BroadcastType.PERSONAL_BEST: parser.parse_personal_best,
    BroadcastType.LEFT_CLAN: parser.parse_clan_leave,
    BroadcastType.EXPELLED: parser.parse_clan_leave,
    BroadcastType.COFFER_DONATION: parser.parse_coffer_transaction,
    BroadcastType.COFFER_WITHDRAWAL: parser.parse_coffer_transaction,
    BroadcastType.HCIM_DEATH: parser.parse_hcim_death,
}


def _broadcast_player_names(kind: BroadcastType, message: str) -> list[str]:
    """Return the RSN(s) involved in a broadcast, used for opt-out checking."""
    if kind == BroadcastType.PK:
        parsed = parser.parse_pk(message)
        return [parsed.winner, parsed.loser] if parsed else []
    parse_fn = _PLAYER_NAME_PARSERS.get(kind)
    if parse_fn:
        parsed = parse_fn(message)
        return [parsed.player_name] if parsed else []
    return []


async def _update_player_rank(
    session: AsyncSession, player_name: str, rank: str
) -> None:
    """Persist a rank change detected from an ingest message."""
    await session.execute(
        update(User)
        .where(
            func.lower(User.rsn) == player_name.lower(),
            User.clan_rank != rank,
        )
        .values(clan_rank=rank, updated_at=datetime.now(timezone.utc))
    )


async def _any_opted_out(session: AsyncSession, player_names: list[str]) -> bool:
    """Return True if any of the given RSNs has opted out of stat storage."""
    if not player_names:
        return False
    result = await session.execute(
        select(User.discord_user_id).where(
            User.rsn.in_(player_names), User.stats_opt_out == True  # noqa: E712
        )
    )
    return result.first() is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _increment_loot_value(
    session: AsyncSession, player_name: str, value: int
) -> None:
    """Increment per-player loot value total in users table."""
    await session.execute(
        update(User)
        .where(func.lower(User.rsn) == player_name.lower())
        .values(
            total_loot_value=User.total_loot_value + value,
            updated_at=_now(),
        )
    )


def _dispatch_doc(event_type: str, player_name: str | None, data: dict) -> dict:
    """Build a dict suitable for Valkey stream dispatch."""
    result: dict = {"type": event_type, "timestamp": _now().isoformat()}
    if player_name:
        result["player_name"] = player_name
    result.update(data)
    return result


async def _handle_broadcast(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
) -> None:
    """Classify and store a clan broadcast message (sender == clan name)."""
    kind = parser.classify(payload.message)

    if await _any_opted_out(session, _broadcast_player_names(kind, payload.message)):
        return

    now = _now()

    if kind == BroadcastType.LOOT:
        parsed = parser.parse_loot(payload.message)
        if parsed:
            data = {
                "item_name": parsed.item_name,
                "coin_value": parsed.coin_value,
                "source": parsed.source,
                "rank": payload.rank,
                "sender": payload.sender,
            }
            session.add(
                Event(
                    type="loot",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            await _increment_loot_value(session, parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Loot: {} got {} ({}gp)",
                clan["guild_id"],
                parsed.player_name,
                parsed.item_name,
                parsed.coin_value,
            )
            await publish(
                valkey,
                "loot",
                _dispatch_doc("loot", parsed.player_name, data),
            )

    elif kind == BroadcastType.LEVEL_UP:
        parsed = parser.parse_level_up(payload.message)
        if parsed:
            data = {"skill": parsed.skill, "new_level": parsed.new_level}
            session.add(
                Event(
                    type="level",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            logger.info(
                "[{}] Level-up: {} reached {} {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.skill,
                parsed.new_level,
            )
            await publish(valkey, "levelup", _dispatch_doc("level", parsed.player_name, data))

    elif kind == BroadcastType.XP_MILESTONE:
        parsed = parser.parse_xp_milestone(payload.message)
        if parsed:
            data = {"skill": parsed.skill, "xp": parsed.xp}
            session.add(
                Event(
                    type="xp_milestone",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            logger.info(
                "[{}] XP milestone: {} reached {:,} XP in {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.xp,
                parsed.skill,
            )
            await publish(
                valkey, "xpmilestone", _dispatch_doc("xp_milestone", parsed.player_name, data)
            )

    elif kind in (
        BroadcastType.QUEST,
        BroadcastType.DIARY,
        BroadcastType.COMBAT_ACHIEVEMENT,
    ):
        parsed = parser.parse_achievement(payload.message)
        if parsed:
            data = {"achievement_type": parsed.kind, "name": parsed.name}
            session.add(
                Event(
                    type=parsed.kind,
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            logger.info(
                "[{}] Achievement: {} - {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.name,
            )
            await publish(
                valkey, "achievement", _dispatch_doc(parsed.kind, parsed.player_name, data)
            )

    elif kind == BroadcastType.PET:
        parsed = parser.parse_pet(payload.message)
        if parsed:
            session.add(
                Event(
                    type="pet",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data={},
                )
            )
            logger.info("[{}] Pet drop: {}", clan["guild_id"], parsed.player_name)
            await publish(valkey, "pet", _dispatch_doc("pet", parsed.player_name, {}))

    elif kind == BroadcastType.NEW_MEMBER:
        parsed = parser.parse_new_member(payload.message)
        if parsed:
            data = {"invited_by": parsed.invited_by}
            session.add(
                Event(
                    type="new_member",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            logger.info(
                "[{}] New member: {} (invited by {})",
                clan["guild_id"],
                parsed.player_name,
                parsed.invited_by,
            )
            await publish(
                valkey, "new_member", _dispatch_doc("new_member", parsed.player_name, data)
            )

    elif kind == BroadcastType.COLLECTION_LOG:
        parsed = parser.parse_collection_log(payload.message)
        if parsed:
            data = {
                "item_name": parsed.item_name,
                "log_slots": parsed.log_slots,
                "log_slots_max": parsed.log_slots_max,
            }
            session.add(
                Event(
                    type="collection_log",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            # Update collection log slots on user (keep max)
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
                _dispatch_doc("collection_log", parsed.player_name, data),
            )

    elif kind == BroadcastType.LOOT_KEY:
        parsed = parser.parse_loot_key(payload.message)
        if parsed:
            data = {"coin_value": parsed.coin_value}
            session.add(
                Event(
                    type="loot_key",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            await _increment_loot_value(session, parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Loot key: {} opened key worth {:,}gp",
                clan["guild_id"],
                parsed.player_name,
                parsed.coin_value,
            )
            await publish(
                valkey, "loot_key", _dispatch_doc("loot_key", parsed.player_name, data)
            )

    elif kind == BroadcastType.CLUE_ITEM:
        parsed = parser.parse_clue_item(payload.message)
        if parsed:
            data = {"item_name": parsed.item_name, "coin_value": parsed.coin_value}
            session.add(
                Event(
                    type="clue_item",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            await _increment_loot_value(session, parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Clue item: {} got {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.item_name,
            )
            await publish(
                valkey, "clue_item", _dispatch_doc("clue_item", parsed.player_name, data)
            )

    elif kind == BroadcastType.PK:
        parsed = parser.parse_pk(payload.message)
        if parsed:
            data = {
                "winner": parsed.winner,
                "loser": parsed.loser,
                "gp_exchanged": parsed.gp_exchanged,
            }
            session.add(
                Event(
                    type="pk",
                    timestamp=now,
                    player_name=parsed.winner,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            logger.info(
                "[{}] PK: {} defeated {} ({} gp)",
                clan["guild_id"],
                parsed.winner,
                parsed.loser,
                parsed.gp_exchanged,
            )
            await publish(valkey, "pk", _dispatch_doc("pk", parsed.winner, data))

    elif kind == BroadcastType.PERSONAL_BEST:
        parsed = parser.parse_personal_best(payload.message)
        if parsed:
            data = {
                "activity": parsed.activity,
                "time_seconds": parsed.time_seconds,
                "variant": parsed.variant or "",
            }
            session.add(
                Event(
                    type="personal_best",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data=data,
                )
            )
            # Upsert leaderboard — keep fastest time
            lb_stmt = (
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
            await session.execute(lb_stmt)
            logger.info(
                "[{}] PB: {} - {} in {}s",
                clan["guild_id"],
                parsed.player_name,
                parsed.activity,
                parsed.time_seconds,
            )
            await publish(
                valkey,
                "personal_best",
                _dispatch_doc("personal_best", parsed.player_name, data),
            )

    elif kind in (BroadcastType.LEFT_CLAN, BroadcastType.EXPELLED):
        parsed = parser.parse_clan_leave(payload.message)
        if parsed:
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
                    _dispatch_doc(
                        "expelled",
                        parsed.player_name,
                        {"expelled_by": parsed.expelled_by},
                    ),
                )
            else:
                logger.info("[{}] Left clan: {}", clan["guild_id"], parsed.player_name)
                await publish(
                    valkey,
                    "left_clan",
                    _dispatch_doc("left_clan", parsed.player_name, {}),
                )

    elif kind in (BroadcastType.COFFER_DONATION, BroadcastType.COFFER_WITHDRAWAL):
        parsed = parser.parse_coffer_transaction(payload.message)
        if parsed:
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
                _dispatch_doc(
                    event_type,
                    parsed.player_name,
                    {"amount": parsed.amount, "is_donation": parsed.is_donation},
                ),
            )

    elif kind == BroadcastType.HCIM_DEATH:
        parsed = parser.parse_hcim_death(payload.message)
        if parsed:
            session.add(
                Event(
                    type="hcim_death",
                    timestamp=now,
                    player_name=parsed.player_name,
                    sender=payload.sender,
                    is_league_world=payload.is_league_world,
                    raw_message=payload.message,
                    data={},
                )
            )
            logger.info("[{}] HCIM death: {}", clan["guild_id"], parsed.player_name)
            await publish(
                valkey, "hcim_death", _dispatch_doc("hcim_death", parsed.player_name, {})
            )

    else:
        # Store unknown broadcasts so no data is silently lost
        session.add(
            Event(
                type="unknown",
                timestamp=now,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data={},
            )
        )
        logger.debug("[{}] Unknown broadcast: {}", clan["guild_id"], payload.message)


@router.post("/ccingest")
async def ingest_chat(
    payloads: list[ClanChatPayload],
    clan: dict = Depends(verify_clan),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Receive a batch of clan chat messages from the TrackScape Connector plugin.

    Configure the plugin's 'URL for sending Clan Chats' (Advanced Settings) to
    point at this endpoint (the root path of the chat subdomain).
    """
    for payload in payloads:
        if await is_duplicate(valkey, clan["key"], payload.sender, payload.message):
            logger.debug(
                "[{}] Duplicate payload from {}, skipping",
                clan["guild_id"],
                payload.sender,
            )
            continue
        is_broadcast = payload.sender == payload.clan_name
        if is_broadcast:
            await _handle_broadcast(payload, clan, session, valkey)
        else:
            await _update_player_rank(session, payload.sender, payload.rank)
            dispatch_data = {
                "player_name": payload.sender,
                "rank": payload.rank,
                "timestamp": _now().isoformat(),
            }
            await publish(valkey, "chat", dispatch_data)

    await session.commit()
    return {"ok": True, "processed": len(payloads)}
