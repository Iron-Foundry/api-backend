"""Parties router — in-memory party management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.db.models import User
from app.dependencies import get_current_user, get_optional_user, get_session
from app.party_store import (
    Party,
    Vibe,
    add_chat_message,
    add_member,
    chat_message_to_dict,
    close_party,
    create_party,
    get_party,
    list_active_parties,
    party_to_dict,
    remove_member,
)
from app.services.discord_party import close_party_embed, edit_party_embed, post_party_embed
from app.services.page_permissions import get_admin_bypass_roles
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/parties", tags=["parties"])


# ── Request models ────────────────────────────────────────────────────────────

class CreatePartyRequest(BaseModel):
    activity: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str | None, Field(max_length=300)] = None
    vibe: Vibe = "chill"
    max_size: Annotated[int, Field(ge=2, le=100)]
    scheduled_at: datetime | None = None
    ttl_hours: Annotated[float, Field(ge=0.5, le=24)] = 4.0
    ping_role_ids: list[str] = []


class UpdatePartyRequest(BaseModel):
    activity: Annotated[str | None, Field(min_length=1, max_length=60)] = None
    description: Annotated[str | None, Field(max_length=300)] = None
    vibe: Vibe | None = None
    max_size: Annotated[int | None, Field(ge=2, le=100)] = None
    scheduled_at: datetime | None = None
    ping_role_ids: list[str] | None = None


class SendChatRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=300)]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_party(party_id: str) -> Party:
    party = get_party(party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    return party


async def _is_staff(uid: int, session: AsyncSession) -> bool:
    roles = await get_effective_roles(uid, session)
    bypass = await get_admin_bypass_roles(session)
    return bool(bypass and any(r in bypass for r in roles))


async def _get_rsn(uid: int, session: AsyncSession) -> str | None:
    result = await session.execute(select(User.rsn).where(User.discord_user_id == uid))
    return result.scalar_one_or_none()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_parties(
    current_user: dict | None = Depends(get_optional_user),
) -> list[dict]:
    """List all non-closed parties. Public."""
    viewer_id = str(current_user["sub"]) if current_user else None
    return [party_to_dict(p, viewer_id) for p in list_active_parties()]


@router.post("", status_code=201)
async def create_new_party(
    body: CreatePartyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a party. The creator is automatically added as leader/first member."""
    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")
    rsn = await _get_rsn(int(current_user["sub"]), session)

    party = create_party(
        leader_id=uid,
        leader_username=username,
        leader_rsn=rsn,
        activity=body.activity.strip(),
        description=body.description.strip() if body.description else None,
        vibe=body.vibe,
        max_size=body.max_size,
        scheduled_at=body.scheduled_at,
        ttl_hours=body.ttl_hours,
        ping_role_ids=body.ping_role_ids,
    )

    message_id = await post_party_embed(party)
    if message_id:
        party.discord_message_id = message_id

    return party_to_dict(party, str(current_user["sub"]))


@router.patch("/{party_id}")
async def update_party(
    party_id: str,
    body: UpdatePartyRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Edit party details. Leader only."""
    party = _require_party(party_id)
    uid = str(current_user["sub"])
    if party.leader_id != uid:
        raise HTTPException(403, "Only the party leader can edit this party")
    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")

    if body.activity is not None:
        party.activity = body.activity.strip()
    if body.description is not None:
        party.description = body.description.strip() or None
    if body.vibe is not None:
        party.vibe = body.vibe
    if body.max_size is not None:
        party.max_size = body.max_size
        # Re-evaluate full/open status after size change
        from app.party_store import _recalc_status
        _recalc_status(party)
    if body.scheduled_at is not None:
        party.scheduled_at = body.scheduled_at
    if body.ping_role_ids is not None:
        party.ping_role_ids = body.ping_role_ids

    await edit_party_embed(party)
    return party_to_dict(party, str(current_user["sub"]))


@router.post("/{party_id}/join")
async def join_party(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Join an open party."""
    party = _require_party(party_id)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is closed")
    if party.status == "full":
        raise HTTPException(409, "Party is full")
    if any(m.user_id == uid for m in party.members):
        raise HTTPException(409, "Already in this party")

    username = current_user.get("username", "Unknown")
    rsn = await _get_rsn(int(current_user["sub"]), session)
    add_member(party, user_id=uid, username=username, rsn=rsn)
    await edit_party_embed(party)
    return party_to_dict(party, str(current_user["sub"]))


@router.delete("/{party_id}/leave")
async def leave_party(
    party_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Leave a party. Leaders cannot leave — they must close the party instead."""
    party = _require_party(party_id)
    uid = str(current_user["sub"])

    if party.leader_id == uid:
        raise HTTPException(400, "Leaders cannot leave — close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")
    if not remove_member(party, uid):
        raise HTTPException(404, "You are not in this party")

    await edit_party_embed(party)
    return party_to_dict(party, str(current_user["sub"]))


@router.delete("/{party_id}")
async def close_party_endpoint(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Close a party. Leader or staff only."""
    party = _require_party(party_id)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")
    if party.leader_id != uid:
        if not await _is_staff(int(current_user["sub"]), session):
            raise HTTPException(403, "Only the party leader or staff can close this party")

    close_party(party)
    await close_party_embed(party)
    return party_to_dict(party, str(current_user["sub"]))


@router.delete("/{party_id}/members/{target_user_id}")
async def kick_member(
    party_id: str,
    target_user_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Kick a member from the party. Leader only."""
    party = _require_party(party_id)
    uid = str(current_user["sub"])

    if party.leader_id != uid:
        raise HTTPException(403, "Only the party leader can kick members")
    if target_user_id == uid:
        raise HTTPException(400, "Cannot kick yourself — close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is closed")
    if not remove_member(party, target_user_id):
        raise HTTPException(404, "Member not found in this party")

    await edit_party_embed(party)
    return party_to_dict(party, str(current_user["sub"]))


@router.get("/{party_id}/chat")
async def get_chat(
    party_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Fetch the most recent 50 chat messages for a party."""
    party = _require_party(party_id)
    return [chat_message_to_dict(m) for m in party.chat[-50:]]


@router.post("/{party_id}/chat", status_code=201)
async def send_chat(
    party_id: str,
    body: SendChatRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Post a chat message to a party. Requires auth; party need not be open."""
    party = _require_party(party_id)
    if party.status == "closed":
        raise HTTPException(409, "Cannot chat in a closed party")
    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")
    msg = add_chat_message(party, user_id=uid, username=username, rsn=None, text=body.text.strip())
    return chat_message_to_dict(msg)
