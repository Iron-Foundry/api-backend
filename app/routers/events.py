from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import CofferEvent, Leaderboard, MembershipEvent, Metric, User
from app.dependencies import get_session, get_valkey, verify_clan
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.ccingest_metrics import collector as ccingest_collector
from app.services.dispatcher import is_duplicate, publish
from app.services.feed_event import insert_feed_event
from app.services.parser import BroadcastType

router = APIRouter(tags=["clan"])

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
    BroadcastType.LEAGUE_RELIC: parser.parse_league_relic,
    BroadcastType.LEAGUE_RANK: parser.parse_league_rank,
    BroadcastType.LEAGUE_AREA: parser.parse_league_area,
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
            User.rsn.in_(player_names),
            User.stats_opt_out == True,  # noqa: E712
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


async def _insert_event(session: AsyncSession, **kwargs: Any) -> None:
    await insert_feed_event(session, **kwargs)


async def _handle_broadcast(
    payload: ClanChatPayload,
    clan: dict,
    session: AsyncSession,
    valkey: Valkey,
) -> None:
    """Classify and store a clan broadcast message (sender == clan name)."""
    kind = parser.classify(payload.message)
    ccingest_collector.record(kind.value)

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
            await _insert_event(
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
                await _increment_loot_value(
                    session, parsed.player_name, parsed.coin_value
                )
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
            await _insert_event(
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
            await publish(
                valkey, "levelup", _dispatch_doc("level", parsed.player_name, data)
            )

    elif kind == BroadcastType.XP_MILESTONE:
        parsed = parser.parse_xp_milestone(payload.message)
        if parsed:
            data = {"skill": parsed.skill, "xp": parsed.xp}
            await _insert_event(
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
                valkey,
                "xpmilestone",
                _dispatch_doc("xp_milestone", parsed.player_name, data),
            )

    elif kind in (
        BroadcastType.QUEST,
        BroadcastType.DIARY,
        BroadcastType.COMBAT_ACHIEVEMENT,
    ):
        parsed = parser.parse_achievement(payload.message)
        if parsed:
            data: dict = {"achievement_type": parsed.kind, "name": parsed.name}
            if parsed.difficulty:
                data["difficulty"] = parsed.difficulty
            await _insert_event(
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
                "[{}] Achievement: {} - {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.name,
            )
            await publish(
                valkey,
                "achievement",
                _dispatch_doc(parsed.kind, parsed.player_name, data),
            )

    elif kind == BroadcastType.PET:
        parsed = parser.parse_pet(payload.message)
        if parsed:
            await _insert_event(
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
            await publish(valkey, "pet", _dispatch_doc("pet", parsed.player_name, {}))

    elif kind == BroadcastType.NEW_MEMBER:
        parsed = parser.parse_new_member(payload.message)
        if parsed:
            data = {"invited_by": parsed.invited_by}
            await _insert_event(
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
                valkey,
                "new_member",
                _dispatch_doc("new_member", parsed.player_name, data),
            )

    elif kind == BroadcastType.COLLECTION_LOG:
        parsed = parser.parse_collection_log(payload.message)
        if parsed:
            data = {
                "item_name": parsed.item_name,
                "log_slots": parsed.log_slots,
                "log_slots_max": parsed.log_slots_max,
            }
            await _insert_event(
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
                    index_elements=["id"],
                    set_={"count": Metric.count + 1, "last_updated": now},
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
            await _insert_event(
                session,
                type="loot_key",
                timestamp=now,
                player_name=parsed.player_name,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
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
            await _insert_event(
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
                await _increment_loot_value(
                    session, parsed.player_name, parsed.coin_value
                )
            logger.info(
                "[{}] Clue item: {} got {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.item_name,
            )
            await publish(
                valkey,
                "clue_item",
                _dispatch_doc("clue_item", parsed.player_name, data),
            )

    elif kind == BroadcastType.PK:
        parsed = parser.parse_pk(payload.message)
        if parsed:
            data = {
                "winner": parsed.winner,
                "loser": parsed.loser,
                "gp_exchanged": parsed.gp_exchanged,
            }
            await _insert_event(
                session,
                type="pk",
                timestamp=now,
                player_name=parsed.winner,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
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
            await _insert_event(
                session,
                type="personal_best",
                timestamp=now,
                player_name=parsed.player_name,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
            )
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
            event_type = (
                "coffer_donation" if parsed.is_donation else "coffer_withdrawal"
            )
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
            await _insert_event(
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
                valkey,
                "hcim_death",
                _dispatch_doc("hcim_death", parsed.player_name, {}),
            )

    elif kind == BroadcastType.LEAGUE_RELIC:
        parsed = parser.parse_league_relic(payload.message)
        if parsed:
            data = {"tier": parsed.tier}
            await _insert_event(
                session,
                type="league_relic",
                timestamp=now,
                player_name=parsed.player_name,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
            )
            logger.info(
                "[{}] League relic: {} unlocked tier {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.tier,
            )
            await publish(
                valkey,
                "league_relic",
                _dispatch_doc("league_relic", parsed.player_name, data),
            )

    elif kind == BroadcastType.LEAGUE_RANK:
        parsed = parser.parse_league_rank(payload.message)
        if parsed:
            data = {"rank": parsed.rank}
            await _insert_event(
                session,
                type="league_rank",
                timestamp=now,
                player_name=parsed.player_name,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
            )
            logger.info(
                "[{}] League rank: {} earned {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.rank,
            )
            await publish(
                valkey,
                "league_rank",
                _dispatch_doc("league_rank", parsed.player_name, data),
            )

    elif kind == BroadcastType.LEAGUE_AREA:
        parsed = parser.parse_league_area(payload.message)
        if parsed:
            data = {"area_count": parsed.area_count}
            await _insert_event(
                session,
                type="league_area",
                timestamp=now,
                player_name=parsed.player_name,
                sender=payload.sender,
                is_league_world=payload.is_league_world,
                raw_message=payload.message,
                data=data,
            )
            logger.info(
                "[{}] League area: {} unlocked area {}",
                clan["guild_id"],
                parsed.player_name,
                parsed.area_count if parsed.area_count is not None else "final",
            )
            await publish(
                valkey,
                "league_area",
                _dispatch_doc("league_area", parsed.player_name, data),
            )

    else:
        await _insert_event(
            session,
            type="unknown",
            timestamp=now,
            sender=payload.sender,
            is_league_world=payload.is_league_world,
            raw_message=payload.message,
            data={},
        )
        await publish(
            valkey,
            "unknown",
            _dispatch_doc("unknown", None, {"raw_message": payload.message}),
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
        is_broadcast = payload.sender == payload.clan_name
        if not is_broadcast:
            await _update_player_rank(session, payload.sender, payload.rank)

        if await is_duplicate(valkey, clan["key"], payload.sender, payload.message):
            logger.debug(
                "[{}] Duplicate payload from {}, skipping",
                clan["guild_id"],
                payload.sender,
            )
            ccingest_collector.record("duplicate")
            continue

        if is_broadcast:
            await _handle_broadcast(payload, clan, session, valkey)
        else:
            ccingest_collector.record("chat")
            dispatch_data = {
                "player_name": payload.sender,
                "rank": payload.rank,
                "raw_message": payload.message,
                "timestamp": _now().isoformat(),
            }
            await publish(valkey, "chat", dispatch_data)

    await session.execute(
        text(
            """
            UPDATE events e
            SET user_id = u.discord_user_id
            FROM (
                SELECT discord_user_id, lower(rsn) AS rsn_lower FROM user_accounts
                UNION
                SELECT discord_user_id, lower(rsn) FROM users WHERE rsn IS NOT NULL
            ) u
            WHERE replace(lower(e.player_name), chr(160), ' ') = u.rsn_lower
              AND e.user_id IS NULL
            """
        )
    )
    await session.commit()
    return {"ok": True, "processed": len(payloads)}
