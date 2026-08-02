import json
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import User
from app.dependencies import verify_clan
from app.services.cc_dispatch import CC_DISPATCH_CHANNEL
from app.services.connection_manager import connection_manager

router = APIRouter(tags=["clan"])


class DiscordMessage(BaseModel):
    sender: str
    message: str
    rank: str | None = None


def _sanitize(text: str) -> str:
    return text.replace("`", "")


def wrap_message(sender: str, message: str, rank: str | None = None) -> str:
    return json.dumps(
        {
            "message_type": "ToClanChat",
            "message": {
                "sender": _sanitize(sender),
                "rank": _sanitize(rank) if rank else rank,
                "message": _sanitize(message),
            },
        }
    )


def split_message(text: str, max_len: int = 78) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    content_max = max_len - 2
    while len(remaining) > max_len:
        split_at = content_max
        if split_at < len(remaining) and remaining[split_at] not in (" ", "\t"):
            boundary = remaining.rfind(" ", 0, split_at)
            if boundary > 0:
                split_at = boundary
        chunks.append(remaining[:split_at].rstrip() + "->")
        remaining = remaining[split_at:].lstrip(" \t")
    chunks.append(remaining)
    return chunks


@router.websocket("/ccdispatch")
async def clan_chat_dispatch(websocket: WebSocket) -> None:
    """Clan chat bridge for the RuneLite plugin.

    A WebSocket, not an HTTP endpoint. Connect with a `verification-code`
    header; the socket closes with 1008 if the key is unknown or revoked.
    Messages relayed from Discord arrive over Valkey pubsub.
    """
    await websocket.accept()
    session_factory = websocket.app.state.session_factory
    verification_code = websocket.headers.get("verification-code")

    guild_id: int | None = None
    discord_user_id: int | None = None
    hide_presence: bool = False

    if verification_code and session_factory:
        async with session_factory() as session:
            result = await session.execute(
                select(
                    User.guild_id,
                    User.discord_user_id,
                    User.hide_presence_notifications,
                ).where(
                    User.api_key == verification_code,
                    User.key_is_active == True,  # noqa: E712
                )
            )
            row = result.one_or_none()
            if row:
                guild_id = row.guild_id
                discord_user_id = row.discord_user_id
                hide_presence = row.hide_presence_notifications

    if guild_id is None or discord_user_id is None:
        await websocket.close(code=1008)
        return

    valkey = websocket.app.state.valkey
    registry = websocket.app.state.ws_registry
    conn_id = connection_manager.connect(websocket, guild_id, verification_code or "")
    await registry.add(guild_id, conn_id)

    async def _publish_presence(event: str) -> None:
        payload = json.dumps(
            {
                "event": event,
                "discord_user_id": discord_user_id,
                "guild_id": guild_id,
                "connection_count": await registry.count(guild_id),
                "hide_presence_notifications": hide_presence,
            }
        )
        try:
            await valkey.publish("foundry:ws_presence", payload)
        except Exception as exc:
            logger.warning("ccdispatch: failed to publish presence event: {}", exc)

    try:
        await websocket.send_json(
            {
                "message_type": "ToClanChat",
                "message": {"sender": "System", "message": "Connected to clan Chat"},
            }
        )
        await _publish_presence("connect")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(conn_id, guild_id)
        await registry.remove(guild_id, conn_id)
        await _publish_presence("disconnect")


@router.post("/ccdispatch")
async def dispatch_to_clan(
    payload: DiscordMessage,
    request: Request,
    conn_id: UUID | None = Query(default=None),
    clan: dict[str, Any] = Depends(verify_clan),
) -> dict[str, Any]:
    """Push a Discord message out to the connected in-game clients.

    Published rather than sent directly: the sockets are spread across every
    gunicorn worker and each one's connection manager sees only its own, so
    `CcDispatchService` in each worker does the delivery. Long messages are
    split into chunks the game chat box accepts, on that side.
    """
    guild_id: int = clan["guild_id"]
    registry = request.app.state.ws_registry
    if conn_id is not None and not await registry.is_connected(guild_id, conn_id):
        raise HTTPException(status_code=404, detail="Client not connected")

    await request.app.state.valkey.publish(
        CC_DISPATCH_CHANNEL,
        json.dumps(
            {
                "guild_id": guild_id,
                "sender": payload.sender,
                "rank": payload.rank,
                "message": payload.message,
                "conn_id": str(conn_id) if conn_id else None,
            }
        ),
    )
    return {"ok": True}
