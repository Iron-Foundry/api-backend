"""Background service that subscribes to Discord clan chat and broadcasts to RuneLite clients."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from valkey.asyncio import Valkey


class DiscordChatService:
    """Subscribes to Valkey pubsub and forwards clan chat messages to WebSocket clients."""

    def __init__(
        self, valkey_uri: str, session_factory: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._valkey_uri = valkey_uri
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="discord-chat-subscriber")
        logger.info("DiscordChatService started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DiscordChatService stopped")

    async def _run(self) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.db.models import Metric
        from app.routers.ccdispatch import split_message
        from app.services.connection_manager import connection_manager

        spacebar_counts: dict[int, int] = {}
        while True:
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe("foundry:discord_chat")
                    logger.info(
                        "DiscordChatService: subscribed to foundry:discord_chat"
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        logger.debug(
                            "DiscordChatService: received raw message: {}", raw["data"]
                        )
                        try:
                            data = json.loads(raw["data"])
                            guild_id: int = int(
                                data.get("guild_id") or data.get("guild_name", 0)
                            )
                            text: str = data["message"]
                            logger.info(
                                "DiscordChatService: forwarding [{}/{}] -> {} client(s)",
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
                                    if self._session_factory is None:
                                        continue
                                    async with self._session_factory() as session:
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
                            logger.warning("DiscordChatService error: {}", exc)
            except asyncio.CancelledError:
                logger.info("DiscordChatService: shutting down")
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "DiscordChatService: connection lost ({}), reconnecting in 5s", exc
                )
                await sub.aclose()
                await asyncio.sleep(5)
