from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from loguru import logger
from pymongo.asynchronous.database import AsyncDatabase
from valkey.asyncio import Valkey

from app.dependencies import get_db, get_valkey, verify_clan
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.dispatcher import publish
from app.services.parser import BroadcastType

router = APIRouter(tags=["clan"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base(payload: ClanChatPayload, clan: dict) -> dict:
    return {
        "clan_name": clan["name"],
        "timestamp": _now(),
        "raw_message": payload.message,
        "sender": payload.sender,
        "rank": payload.rank,
        "is_league_world": payload.is_league_world,
    }


async def _handle_broadcast(
    payload: ClanChatPayload,
    clan: dict,
    db: AsyncDatabase,
    valkey: Valkey,
) -> None:
    """Classify and store a clan broadcast message (sender == clan name)."""
    kind = parser.classify(payload.message)

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
            logger.info(
                "[{}] Loot: {} got {} ({}gp)",
                clan["name"],
                parsed.player_name,
                parsed.item_name,
                parsed.coin_value,
            )
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "loot", dispatch_data)

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
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "levelup", dispatch_data)

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
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "achievement", dispatch_data)

    elif kind == BroadcastType.PET:
        parsed = parser.parse_pet(payload.message)
        if parsed:
            doc = {**_base(payload, clan), "player_name": parsed.player_name}
            await db["pet_events"].insert_one(doc)
            logger.info("[{}] Pet drop: {}", clan["name"], parsed.player_name)
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "pet", dispatch_data)

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
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "new_member", dispatch_data)

    else:
        # Store unknown broadcasts so no data is silently lost
        await db["unknown_broadcasts"].insert_one(_base(payload, clan))
        logger.debug("[{}] Unknown broadcast: {}", clan["name"], payload.message)


@router.post("/")
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
        is_broadcast = payload.sender == payload.clan_name
        if is_broadcast:
            await _handle_broadcast(payload, clan, db, valkey)
        else:
            doc = {**_base(payload, clan), "player_name": payload.sender}
            await db["chat_events"].insert_one(doc)
            dispatch_data = {
                k: v
                for k, v in doc.items()
                if k != "_id" and not isinstance(v, datetime)
            }
            dispatch_data["timestamp"] = doc["timestamp"].isoformat()
            await publish(valkey, "chat", dispatch_data)

    return {"ok": True, "processed": len(payloads)}
