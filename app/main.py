import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from valkey.asyncio import Valkey

from app.db import create_engine, create_session_factory
from app.routers import assets, auth, badges, ccdispatch, clan, config, content, events, members, staff, surveys
from app.routers.ccdispatch import split_message
from app.services.connection_manager import connection_manager
from app.services.name_change import WomNameChangeService

DATABASE_URL = os.getenv("DATABASE_URL", "")
VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")
WOM_GROUP_ID = os.getenv("WOM_GROUP_ID")
WOM_GROUP_KEY = os.getenv("WOM_GROUP_KEY")
WOM_CLAN_NAME = os.getenv("WOM_CLAN_NAME", "Iron Foundry")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
_ALLOWED_ORIGINS = [o.strip() for o in FRONTEND_URL.split(",") if o.strip()]


async def _discord_chat_subscriber(valkey_uri: str, session_factory) -> None:  # type: ignore[no-untyped-def]
    """Subscribe to Discord clan chat messages and broadcast them to RuneLite clients."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.models import Metric

    spacebar_counts: dict[int, int] = {}
    while True:
        sub = Valkey.from_url(valkey_uri, socket_timeout=None)
        try:
            async with sub.pubsub() as ps:
                await ps.subscribe("foundry:discord_chat")
                logger.info(
                    "discord_chat_subscriber: subscribed to foundry:discord_chat"
                )
                async for raw in ps.listen():
                    if raw["type"] != "message":
                        continue
                    logger.debug(
                        "discord_chat_subscriber: received raw message: {}", raw["data"]
                    )
                    try:
                        data = json.loads(raw["data"])
                        guild_id: int = int(
                            data.get("guild_id") or data.get("guild_name", 0)
                        )
                        text: str = data["message"]
                        logger.info(
                            "discord_chat_subscriber: forwarding [{}/{}] → {} client(s)",
                            guild_id,
                            data.get("sender", "?"),
                            connection_manager.connection_count(guild_id),
                        )
                        for part in split_message(text):
                            msg = json.dumps(
                                {
                                    "message_type": "ToClanChat",
                                    "message": {
                                        "sender": data["sender"],
                                        "rank": data.get("rank"),
                                        "message": part,
                                    },
                                }
                            )
                            await connection_manager.broadcast(guild_id, msg)
                        if not text.strip():
                            spacebar_counts[guild_id] = (
                                spacebar_counts.get(guild_id, 0) + 1
                            )
                            count = spacebar_counts[guild_id]
                            if count == 2:
                                sys_text: str | None = "Spacebar check started!"
                            elif count > 2:
                                sys_text = f"Spacebar check: {count}"
                            else:
                                sys_text = None
                            if sys_text:
                                await connection_manager.broadcast(
                                    guild_id,
                                    json.dumps(
                                        {
                                            "message_type": "ToClanChat",
                                            "message": {
                                                "sender": "System",
                                                "rank": None,
                                                "message": sys_text,
                                            },
                                        }
                                    ),
                                )
                            if count >= 2:
                                record_id = f"longest_spacebar_check_{guild_id}"
                                now = datetime.now(timezone.utc)
                                stmt = (
                                    pg_insert(Metric)
                                    .values(
                                        id=record_id,
                                        count=count,
                                        achieved_at=now,
                                        last_updated=now,
                                    )
                                    .on_conflict_do_update(
                                        index_elements=["id"],
                                        set_={
                                            "count": count,
                                            "last_updated": now,
                                        },
                                        where=Metric.count < count,
                                    )
                                )
                                async with session_factory() as session:
                                    await session.execute(stmt)
                                    await session.commit()
                        else:
                            prev = spacebar_counts.get(guild_id, 0)
                            spacebar_counts[guild_id] = 0
                            if prev >= 2:
                                await connection_manager.broadcast(
                                    guild_id,
                                    json.dumps(
                                        {
                                            "message_type": "ToClanChat",
                                            "message": {
                                                "sender": "System",
                                                "rank": None,
                                                "message": f"Spacebar check failed at {prev}!",
                                            },
                                        }
                                    ),
                                )
                    except Exception as exc:
                        logger.warning("discord_chat_subscriber error: {}", exc)
        except asyncio.CancelledError:
            logger.info("discord_chat_subscriber: shutting down")
            await sub.aclose()
            return
        except Exception as exc:
            logger.warning(
                "discord_chat_subscriber: connection lost ({}), reconnecting in 5s", exc
            )
            await sub.aclose()
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DATABASE_URL:
        logger.info("Connecting to PostgreSQL...")
        engine = create_engine(DATABASE_URL)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
    else:
        logger.warning("DATABASE_URL not set — PostgreSQL disabled")
        app.state.engine = None
        app.state.session_factory = None

    logger.info("Connecting to Valkey at {}...", VALKEY_URI)
    app.state.valkey = Valkey.from_url(VALKEY_URI)
    subscriber_task = asyncio.create_task(
        _discord_chat_subscriber(VALKEY_URI, app.state.session_factory),
        name="discord-chat-subscriber",
    )
    if WOM_GROUP_ID:
        wom_service: WomNameChangeService | None = WomNameChangeService(
            app.state.session_factory, int(WOM_GROUP_ID), WOM_GROUP_KEY, WOM_CLAN_NAME
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
    if app.state.engine:
        logger.info("Closing PostgreSQL connection...")
        await app.state.engine.dispose()
    logger.info("Closing Valkey connection...")
    await app.state.valkey.aclose()


app = FastAPI(title="The Foundry API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(clan.router)
app.include_router(config.router)
app.include_router(events.router)
app.include_router(ccdispatch.router)
app.include_router(members.router)
app.include_router(staff.router)
app.include_router(surveys.router)
app.include_router(badges.router)
app.include_router(content.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
