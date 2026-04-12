import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from pymongo import AsyncMongoClient
from valkey.asyncio import Valkey

from app.models.users import ensure_users_indexes
from app.routers import ccdispatch, events
from app.services.connection_manager import connection_manager

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "foundry")
VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")


async def _discord_chat_subscriber(valkey_uri: str) -> None:
    """Subscribe to Discord clan chat messages and broadcast them to RuneLite clients."""
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
                        logger.info(
                            "discord_chat_subscriber: forwarding [{}/{}] → {} client(s)",
                            data.get("guild_name", "?"),
                            data.get("sender", "?"),
                            connection_manager.connection_count(data.get("guild_name", "")),
                        )
                        msg = json.dumps({
                            "message_type": "ToClanChat",
                            "message": {
                                "sender": data["sender"],
                                "message": data["message"],
                            },
                        })
                        await connection_manager.broadcast(data["guild_name"], msg)
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
        _discord_chat_subscriber(VALKEY_URI),
        name="discord-chat-subscriber",
    )
    yield
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
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
