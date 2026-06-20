from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_current_user, get_session, get_valkey
from app.party_store import add_member, party_to_dict, remove_member
from app.services.discord_party import edit_party_embed

from ._helpers import JoinPartyRequest, get_rsn, notify, require_party

router = APIRouter()


@router.post("/{party_id}/join")
async def join_party(
    party_id: str,
    body: JoinPartyRequest = Body(default_factory=JoinPartyRequest),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Join an open party."""
    party = await require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is closed")
    if party.status == "full":
        raise HTTPException(409, "Party is full")
    if any(m.user_id == uid for m in party.members):
        raise HTTPException(409, "Already in this party")

    existing_ids = [m.user_id for m in party.members]
    username = current_user.get("username", "Unknown")
    rsn = await get_rsn(int(current_user["sub"]), session, body.rsn_override)
    await add_member(session, party, user_id=uid, username=username, rsn=rsn)
    await edit_party_embed(party)

    joiner_name = rsn or username
    await notify(
        valkey,
        existing_ids,
        f"**{joiner_name}** joined **{party.activity}**.\nSpots: {len(party.members)}/{party.max_size}",
    )
    return party_to_dict(party, uid)


@router.delete("/{party_id}/leave")
async def leave_party(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Leave a party. Leaders cannot leave - they must close the party instead."""
    party = await require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.leader_id == uid:
        raise HTTPException(400, "Leaders cannot leave - close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")

    leaving_member = next((m for m in party.members if m.user_id == uid), None)
    leaving_name = (
        (leaving_member.rsn or leaving_member.username)
        if leaving_member
        else current_user.get("username", "Unknown")
    )
    if not await remove_member(session, party, uid):
        raise HTTPException(404, "You are not in this party")

    await edit_party_embed(party)

    remaining_ids = [m.user_id for m in party.members]
    await notify(
        valkey,
        remaining_ids,
        f"**{leaving_name}** left **{party.activity}**.\nSpots: {len(party.members)}/{party.max_size}",
    )
    return party_to_dict(party, uid)


@router.delete("/{party_id}/members/{user_id}")
async def kick_member(
    party_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Kick a member from the party. Leader only."""
    party = await require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.leader_id != uid:
        raise HTTPException(403, "Only the party leader can kick members")
    if user_id == uid:
        raise HTTPException(400, "Cannot kick yourself - close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is closed")

    kicked_member = next((m for m in party.members if m.user_id == user_id), None)
    kicked_name = (
        (kicked_member.rsn or kicked_member.username) if kicked_member else "A member"
    )
    if not await remove_member(session, party, user_id):
        raise HTTPException(404, "Member not found in this party")

    await edit_party_embed(party)

    remaining_ids = [m.user_id for m in party.members]
    await notify(
        valkey,
        [user_id],
        f"You were removed from **{party.activity}** by the party leader.",
    )
    await notify(
        valkey,
        remaining_ids,
        f"**{kicked_name}** was removed from **{party.activity}** by the leader.",
    )
    return party_to_dict(party, uid)
