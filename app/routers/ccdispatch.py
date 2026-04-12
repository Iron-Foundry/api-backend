import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.dependencies import verify_clan
from app.services.connection_manager import connection_manager

router = APIRouter(tags=["clan"])


class DiscordMessage(BaseModel):
    sender: str
    message: str


def _wrap(sender: str, message: str) -> str:
    return json.dumps(
        {
            "message_type": "ToClanChat",
            "message": {"sender": sender, "message": message},
        }
    )


@router.websocket("/ccdispatch")
async def clan_chat_dispatch(websocket: WebSocket) -> None:
    db = websocket.app.state.db
    verification_code = websocket.headers.get("verification-code")
    doc = await db["user_keys"].find_one({"key": verification_code, "is_active": True}) if verification_code else None
    if not doc:
        await websocket.close(code=1008)
        return
    guild_name: str = doc["guild_name"]
    conn_id = await connection_manager.connect(websocket, guild_name, verification_code)
    await websocket.send_text(json.dumps({
        "message_type": "Connected",
        "message": {"conn_id": str(conn_id), "guild": guild_name},
    }))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(conn_id, guild_name)


@router.post("/ccdispatch")
async def dispatch_to_clan(
    payload: DiscordMessage,
    conn_id: UUID | None = Query(default=None),
    clan: dict = Depends(verify_clan),
) -> dict:
    msg = _wrap(payload.sender, payload.message)
    if conn_id is not None:
        delivered = await connection_manager.send_to(conn_id, clan["name"], msg)
        if not delivered:
            raise HTTPException(status_code=404, detail="Client not connected")
    else:
        await connection_manager.broadcast(clan["name"], msg)
    return {"ok": True}
