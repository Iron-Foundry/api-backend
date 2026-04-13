import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from loguru import logger
from pymongo import AsyncMongoClient
from valkey.asyncio import Valkey

from app.models.users import ensure_users_indexes
from app.routers import ccdispatch, events
from app.routers.ccdispatch import split_message
from app.services.connection_manager import connection_manager
from app.services.name_change import WomNameChangeService

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "foundry")
VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")
WOM_GROUP_ID = os.getenv("WOM_GROUP_ID")
WOM_GROUP_KEY = os.getenv("WOM_GROUP_KEY")
WOM_CLAN_NAME = os.getenv("WOM_CLAN_NAME", "Iron Foundry")


async def _discord_chat_subscriber(valkey_uri: str, db) -> None:  # type: ignore[no-untyped-def]
    """Subscribe to Discord clan chat messages and broadcast them to RuneLite clients."""
    spacebar_counts: dict[str, int] = {}
    while True:
        sub = Valkey.from_url(valkey_uri, socket_timeout=None)
        try:
            async with sub.pubsub() as ps:
                await ps.subscribe("foundry:discord_chat")
                logger.info("discord_chat_subscriber: subscribed to foundry:discord_chat")
                async for raw in ps.listen():
                    if raw["type"] != "message":
                        continue
                    logger.debug("discord_chat_subscriber: received raw message: {}", raw["data"])
                    try:
                        data = json.loads(raw["data"])
                        guild: str = data["guild_name"]
                        text: str = data["message"]
                        logger.info(
                            "discord_chat_subscriber: forwarding [{}/{}] → {} client(s)",
                            guild,
                            data.get("sender", "?"),
                            connection_manager.connection_count(guild),
                        )
                        for part in split_message(text):
                            msg = json.dumps({
                                "message_type": "ToClanChat",
                                "message": {
                                    "sender": data["sender"],
                                    "rank": data.get("rank"),
                                    "message": part,
                                },
                            })
                            await connection_manager.broadcast(guild, msg)
                        if not text.strip():
                            spacebar_counts[guild] = spacebar_counts.get(guild, 0) + 1
                            count = spacebar_counts[guild]
                            if count == 2:
                                sys_text: str | None = "Spacebar check started!"
                            elif count > 2:
                                sys_text = f"Spacebar check: {count}"
                            else:
                                sys_text = None
                            if sys_text:
                                await connection_manager.broadcast(guild, json.dumps({
                                    "message_type": "ToClanChat",
                                    "message": {"sender": "System", "rank": None, "message": sys_text},
                                }))
                            if count >= 2:
                                record_id = f"longest_spacebar_check_{guild}"
                                rec = await db["fun_metrics"].find_one({"_id": record_id})
                                if not rec or count > rec["count"]:
                                    await db["fun_metrics"].update_one(
                                        {"_id": record_id},
                                        {"$set": {"count": count, "guild_name": guild, "achieved_at": datetime.now(timezone.utc)}},
                                        upsert=True,
                                    )
                        else:
                            prev = spacebar_counts.get(guild, 0)
                            spacebar_counts[guild] = 0
                            if prev >= 2:
                                await connection_manager.broadcast(guild, json.dumps({
                                    "message_type": "ToClanChat",
                                    "message": {"sender": "System", "rank": None, "message": f"Spacebar check failed at {prev}!"},
                                }))
                    except Exception as exc:
                        logger.warning("discord_chat_subscriber error: {}", exc)
        except asyncio.CancelledError:
            logger.info("discord_chat_subscriber: shutting down")
            await sub.aclose()
            return
        except Exception as exc:
            logger.warning("discord_chat_subscriber: connection lost ({}), reconnecting in 5s", exc)
            await sub.aclose()
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to MongoDB at {}...", MONGO_URI)
    app.state.mongo = AsyncMongoClient(MONGO_URI)
    app.state.db = app.state.mongo[MONGO_DB]
    await ensure_users_indexes(app.state.db)
    logger.info("Connecting to Valkey at {}...", VALKEY_URI)
    app.state.valkey = Valkey.from_url(VALKEY_URI)
    subscriber_task = asyncio.create_task(
        _discord_chat_subscriber(VALKEY_URI, app.state.db),
        name="discord-chat-subscriber",
    )
    if WOM_GROUP_ID:
        wom_service: WomNameChangeService | None = WomNameChangeService(
            app.state.db, int(WOM_GROUP_ID), WOM_GROUP_KEY, WOM_CLAN_NAME
        )
        await wom_service.start()
    else:
        logger.warning("WOM_GROUP_ID not set — name change service disabled")
        wom_service = None
    yield
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    if wom_service:
        await wom_service.stop()
    logger.info("Closing MongoDB connection...")
    await app.state.mongo.aclose()
    logger.info("Closing Valkey connection...")
    await app.state.valkey.aclose()


app = FastAPI(title="The Foundry API", lifespan=lifespan)

app.include_router(events.router)
app.include_router(ccdispatch.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
