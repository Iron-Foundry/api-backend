from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from pymongo.asynchronous.database import AsyncDatabase
from valkey.asyncio import Valkey

from app.dependencies import get_db, get_valkey, verify_clan
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


async def _update_player_rank(db: AsyncDatabase, player_name: str, rank: str) -> None:
    """Persist a rank change detected from an ingest message.

    Only writes when the stored rank differs — if a player's rank changed
    in-game this keeps the users collection in sync.
    """
    await db["users"].update_one(
        {"rsn": player_name, "clan_rank": {"$ne": rank}},
        {"$set": {"clan_rank": rank, "updated_at": datetime.now(timezone.utc)}},
    )


async def _any_opted_out(db: AsyncDatabase, player_names: list[str]) -> bool:
    """Return True if any of the given RSNs has opted out of stat storage."""
    if not player_names:
        return False
    doc = await db["users"].find_one(
        {"rsn": {"$in": player_names}, "stats_opt_out": True}, {"_id": 1}
    )
    return doc is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _increment_loot_value(db: AsyncDatabase, clan_name: str, player_name: str, value: int) -> None:
    """Increment per-player and clan-wide loot value totals."""
    now = _now()
    await db["loot_totals"].update_one(
        {"clan_name": clan_name, "player_name": player_name},
        {"$inc": {"total_value": value}, "$set": {"last_updated": now}},
        upsert=True,
    )
    await db["fun_metrics"].update_one(
        {"_id": f"clan_loot_total_{clan_name}"},
        {"$inc": {"total_value": value}, "$set": {"clan_name": clan_name, "last_updated": now}},
        upsert=True,
    )


def _base(payload: ClanChatPayload, clan: dict) -> dict:
    return {
        "clan_name": clan["name"],
        "timestamp": _now(),
        "raw_message": payload.message,
        "sender": payload.sender,
        "rank": payload.rank,
        "is_league_world": payload.is_league_world,
    }


def _dispatch_doc(doc: dict) -> dict:
    """Strip MongoDB-internal fields and serialise datetime for stream dispatch."""
    result = {k: v for k, v in doc.items() if k != "_id" and not isinstance(v, datetime)}
    result["timestamp"] = doc["timestamp"].isoformat()
    return result


async def _handle_broadcast(
    payload: ClanChatPayload,
    clan: dict,
    db: AsyncDatabase,
    valkey: Valkey,
) -> None:
    """Classify and store a clan broadcast message (sender == clan name)."""
    kind = parser.classify(payload.message)

    if await _any_opted_out(db, _broadcast_player_names(kind, payload.message)):
        return

    if kind == BroadcastType.LOOT:
        parsed = parser.parse_loot(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "item_name": parsed.item_name,
                "coin_value": parsed.coin_value,
                "source": parsed.source,
            }
            await db["loot_events"].insert_one(doc)
            await _increment_loot_value(db, clan["name"], parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Loot: {} got {} ({}gp)",
                clan["name"],
                parsed.player_name,
                parsed.item_name,
                parsed.coin_value,
            )
            await publish(valkey, "loot", _dispatch_doc(doc))

    elif kind == BroadcastType.LEVEL_UP:
        parsed = parser.parse_level_up(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "skill": parsed.skill,
                "new_level": parsed.new_level,
            }
            await db["level_events"].insert_one(doc)
            logger.info(
                "[{}] Level-up: {} reached {} {}",
                clan["name"],
                parsed.player_name,
                parsed.skill,
                parsed.new_level,
            )
            await publish(valkey, "levelup", _dispatch_doc(doc))

    elif kind == BroadcastType.XP_MILESTONE:
        parsed = parser.parse_xp_milestone(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "skill": parsed.skill,
                "xp": parsed.xp,
            }
            await db["xp_events"].insert_one(doc)
            logger.info(
                "[{}] XP milestone: {} reached {:,} XP in {}",
                clan["name"],
                parsed.player_name,
                parsed.xp,
                parsed.skill,
            )
            await publish(valkey, "xpmilestone", _dispatch_doc(doc))

    elif kind in (
        BroadcastType.QUEST,
        BroadcastType.DIARY,
        BroadcastType.COMBAT_ACHIEVEMENT,
    ):
        parsed = parser.parse_achievement(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "achievement_type": parsed.kind,
                "name": parsed.name,
            }
            await db["achievement_events"].insert_one(doc)
            logger.info(
                "[{}] Achievement: {} - {}",
                clan["name"],
                parsed.player_name,
                parsed.name,
            )
            await publish(valkey, "achievement", _dispatch_doc(doc))

    elif kind == BroadcastType.PET:
        parsed = parser.parse_pet(payload.message)
        if parsed:
            doc = {**_base(payload, clan), "player_name": parsed.player_name}
            await db["pet_events"].insert_one(doc)
            logger.info("[{}] Pet drop: {}", clan["name"], parsed.player_name)
            await publish(valkey, "pet", _dispatch_doc(doc))

    elif kind == BroadcastType.NEW_MEMBER:
        parsed = parser.parse_new_member(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "invited_by": parsed.invited_by,
            }
            await db["member_events"].insert_one(doc)
            logger.info(
                "[{}] New member: {} (invited by {})",
                clan["name"],
                parsed.player_name,
                parsed.invited_by,
            )
            await publish(valkey, "new_member", _dispatch_doc(doc))

    elif kind == BroadcastType.COLLECTION_LOG:
        parsed = parser.parse_collection_log(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "item_name": parsed.item_name,
                "log_slots": parsed.log_slots,
                "log_slots_max": parsed.log_slots_max,
            }
            await db["collection_log_events"].insert_one(doc)
            await db["collection_log_counts"].update_one(
                {"clan_name": clan["name"], "player_name": parsed.player_name},
                {
                    "$max": {"log_slots": parsed.log_slots},
                    "$set": {
                        "clan_name": clan["name"],
                        "player_name": parsed.player_name,
                        "log_slots_max": parsed.log_slots_max,
                    },
                },
                upsert=True,
            )
            logger.info(
                "[{}] Collection log: {} - {} (slot {})",
                clan["name"],
                parsed.player_name,
                parsed.item_name,
                parsed.log_slots,
            )
            await publish(valkey, "collection_log", _dispatch_doc(doc))

    elif kind == BroadcastType.LOOT_KEY:
        parsed = parser.parse_loot_key(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "coin_value": parsed.coin_value,
            }
            await db["loot_key_events"].insert_one(doc)
            await _increment_loot_value(db, clan["name"], parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Loot key: {} opened key worth {:,}gp",
                clan["name"],
                parsed.player_name,
                parsed.coin_value,
            )
            await publish(valkey, "loot_key", _dispatch_doc(doc))

    elif kind == BroadcastType.CLUE_ITEM:
        parsed = parser.parse_clue_item(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "item_name": parsed.item_name,
                "coin_value": parsed.coin_value,
            }
            await db["clue_events"].insert_one(doc)
            await _increment_loot_value(db, clan["name"], parsed.player_name, parsed.coin_value)
            logger.info(
                "[{}] Clue item: {} got {}",
                clan["name"],
                parsed.player_name,
                parsed.item_name,
            )
            await publish(valkey, "clue_item", _dispatch_doc(doc))

    elif kind == BroadcastType.PK:
        parsed = parser.parse_pk(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "winner": parsed.winner,
                "loser": parsed.loser,
                "gp_exchanged": parsed.gp_exchanged,
            }
            await db["pk_events"].insert_one(doc)
            logger.info(
                "[{}] PK: {} defeated {} ({} gp)",
                clan["name"],
                parsed.winner,
                parsed.loser,
                parsed.gp_exchanged,
            )
            await publish(valkey, "pk", _dispatch_doc(doc))

    elif kind == BroadcastType.PERSONAL_BEST:
        parsed = parser.parse_personal_best(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "activity": parsed.activity,
                "time_seconds": parsed.time_seconds,
                "variant": parsed.variant,
            }
            await db["personal_best_events"].insert_one(doc)
            await db["personal_bests"].update_one(
                {
                    "clan_name": clan["name"],
                    "player_name": parsed.player_name,
                    "activity": parsed.activity,
                    "variant": parsed.variant,
                },
                {
                    "$min": {"time_seconds": parsed.time_seconds},
                    "$set": {
                        "clan_name": clan["name"],
                        "player_name": parsed.player_name,
                        "activity": parsed.activity,
                        "variant": parsed.variant,
                    },
                },
                upsert=True,
            )
            logger.info(
                "[{}] PB: {} - {} in {}s",
                clan["name"],
                parsed.player_name,
                parsed.activity,
                parsed.time_seconds,
            )
            await publish(valkey, "personal_best", _dispatch_doc(doc))

    elif kind in (BroadcastType.LEFT_CLAN, BroadcastType.EXPELLED):
        parsed = parser.parse_clan_leave(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "expelled_by": parsed.expelled_by,
            }
            await db["membership_events"].insert_one(doc)
            if parsed.expelled_by:
                logger.info(
                    "[{}] Expelled: {} by {}",
                    clan["name"],
                    parsed.player_name,
                    parsed.expelled_by,
                )
                await publish(valkey, "expelled", _dispatch_doc(doc))
            else:
                logger.info("[{}] Left clan: {}", clan["name"], parsed.player_name)
                await publish(valkey, "left_clan", _dispatch_doc(doc))

    elif kind in (BroadcastType.COFFER_DONATION, BroadcastType.COFFER_WITHDRAWAL):
        parsed = parser.parse_coffer_transaction(payload.message)
        if parsed:
            doc = {
                **_base(payload, clan),
                "player_name": parsed.player_name,
                "amount": parsed.amount,
                "is_donation": parsed.is_donation,
            }
            await db["coffer_events"].insert_one(doc)
            logger.info(
                "[{}] Coffer {}: {} {:,}gp",
                clan["name"],
                "deposit" if parsed.is_donation else "withdrawal",
                parsed.player_name,
                parsed.amount,
            )
            event_type = "coffer_donation" if parsed.is_donation else "coffer_withdrawal"
            await publish(valkey, event_type, _dispatch_doc(doc))

    elif kind == BroadcastType.HCIM_DEATH:
        parsed = parser.parse_hcim_death(payload.message)
        if parsed:
            doc = {**_base(payload, clan), "player_name": parsed.player_name}
            await db["hcim_death_events"].insert_one(doc)
            logger.info("[{}] HCIM death: {}", clan["name"], parsed.player_name)
            await publish(valkey, "hcim_death", _dispatch_doc(doc))

    else:
        # Store unknown broadcasts so no data is silently lost
        await db["unknown_broadcasts"].insert_one(_base(payload, clan))
        logger.debug("[{}] Unknown broadcast: {}", clan["name"], payload.message)


@router.post("/ccingest")
async def ingest_chat(
    payloads: list[ClanChatPayload],
    clan: dict = Depends(verify_clan),
    db: AsyncDatabase = Depends(get_db),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Receive a batch of clan chat messages from the TrackScape Connector plugin.

    Configure the plugin's 'URL for sending Clan Chats' (Advanced Settings) to
    point at this endpoint (the root path of the chat subdomain).
    """
    for payload in payloads:
        if await is_duplicate(valkey, clan["key"], payload.sender, payload.message):
            logger.debug(
                "[{}] Duplicate payload from {}, skipping", clan["name"], payload.sender
            )
            continue
        is_broadcast = payload.sender == payload.clan_name
        if is_broadcast:
            await _handle_broadcast(payload, clan, db, valkey)
        else:
            await _update_player_rank(db, payload.sender, payload.rank)
            dispatch_data = {
                **_base(payload, clan),
                "player_name": payload.sender,
                "timestamp": _now().isoformat(),
            }
            await publish(valkey, "chat", dispatch_data)

    return {"ok": True, "processed": len(payloads)}
