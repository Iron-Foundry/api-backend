import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import User
from app.dependencies import verify_clan
from app.services.connection_manager import connection_manager

router = APIRouter(tags=["clan"])


class DiscordMessage(BaseModel):
    sender: str
    message: str
    rank: str | None = None


def _sanitize(text: str) -> str:
    return text.replace("`", "")


def _wrap(sender: str, message: str, rank: str | None = None) -> str:
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
    conn_id = connection_manager.connect(websocket, guild_id, verification_code or "")

    async def _publish_presence(event: str) -> None:
        payload = json.dumps(
            {
                "event": event,
                "discord_user_id": discord_user_id,
                "guild_id": guild_id,
                "connection_count": connection_manager.connection_count(guild_id),
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
        await _publish_presence("disconnect")


@router.post("/ccdispatch")
async def dispatch_to_clan(
    payload: DiscordMessage,
    conn_id: UUID | None = Query(default=None),
    clan: dict = Depends(verify_clan),
) -> dict:
    guild_id: int = clan["guild_id"]
    for part in split_message(payload.message):
        msg = _wrap(payload.sender, part, payload.rank)
        if conn_id is not None:
            delivered = await connection_manager.send_to(conn_id, guild_id, msg)
            if not delivered:
                raise HTTPException(status_code=404, detail="Client not connected")
        else:
            await connection_manager.broadcast(guild_id, msg)
    return {"ok": True}
