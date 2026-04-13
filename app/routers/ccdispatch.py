import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel

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
    content_max = max_len - 2  # reserve 2 chars for "->"
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
    db = websocket.app.state.db
    verification_code = websocket.headers.get("verification-code")
    doc = await db["user_keys"].find_one({"key": verification_code, "is_active": True}) if verification_code else None
    if not doc:
        await websocket.close(code=1008)
        return
    guild_name: str = doc["guild_name"]
    discord_user_id: int = doc["discord_user_id"]
    valkey = websocket.app.state.valkey
    conn_id = connection_manager.connect(websocket, guild_name, verification_code)

    async def _publish_presence(event: str) -> None:
        payload = json.dumps({
            "event": event,
            "discord_user_id": discord_user_id,
            "guild_name": guild_name,
            "connection_count": connection_manager.connection_count(guild_name),
        })
        try:
            await valkey.publish("foundry:ws_presence", payload)
        except Exception as exc:
            logger.warning("ccdispatch: failed to publish presence event: {}", exc)

    try:
        await websocket.send_json({
            "message_type": "ToClanChat",
            "message": {"sender": "System", "message": f"Connected to {guild_name} Chat"},
        })
        await _publish_presence("connect")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(conn_id, guild_name)
        await _publish_presence("disconnect")


@router.post("/ccdispatch")
async def dispatch_to_clan(
    payload: DiscordMessage,
    conn_id: UUID | None = Query(default=None),
    clan: dict = Depends(verify_clan),
) -> dict:
    for part in split_message(payload.message):
        msg = _wrap(payload.sender, part, payload.rank)
        if conn_id is not None:
            delivered = await connection_manager.send_to(conn_id, clan["name"], msg)
            if not delivered:
                raise HTTPException(status_code=404, detail="Client not connected")
        else:
            await connection_manager.broadcast(clan["name"], msg)
    return {"ok": True}
