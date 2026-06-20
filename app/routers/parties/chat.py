from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import PartyChatMessageDB
from app.dependencies import get_current_user, get_session, get_valkey
from app.party_store import add_chat_message, chat_message_to_dict, get_chat_messages

from ._helpers import SendChatRequest, notify, require_party

router = APIRouter()


@router.get("/{party_id}/chat")
async def get_chat(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Fetch the most recent 50 chat messages for a party."""
    await require_party(party_id, session)
    messages = await get_chat_messages(session, party_id)
    return [chat_message_to_dict(m) for m in messages]


@router.post("/{party_id}/chat", status_code=201)
async def send_chat(
    party_id: str,
    body: SendChatRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Post a chat message to a party."""
    party = await require_party(party_id, session)
    if party.status == "closed":
        raise HTTPException(409, "Cannot chat in a closed party")

    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")

    prior_count = (
        await session.execute(
            select(func.count(PartyChatMessageDB.id)).where(
                PartyChatMessageDB.party_id == party_id,
                PartyChatMessageDB.user_id == uid,
            )
        )
    ).scalar()
    is_first_message = prior_count == 0

    msg = await add_chat_message(
        session,
        party_id,
        user_id=uid,
        username=username,
        rsn=None,
        text=body.text.strip(),
    )

    if is_first_message:
        others = [m.user_id for m in party.members if m.user_id != uid]
        await notify(
            valkey,
            others,
            f"**{username}** sent their first message in **{party.activity}** party chat!\n"
            f"ironfoundry.cc/parties/{party_id}",
        )

    return chat_message_to_dict(msg)
