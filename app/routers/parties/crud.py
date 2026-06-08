from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_current_user, get_optional_user, get_session, get_valkey
from app.party_store import _recalc_status, close_party, create_party, list_active_parties, party_to_dict
from app.services.discord_party import close_party_embed, edit_party_embed, post_party_embed

from ._helpers import (
    CreatePartyRequest,
    UpdatePartyRequest,
    dispatch_party_notifications,
    get_rsn,
    is_staff,
    notify,
    require_party,
    resolve_scheduled_at,
)

router = APIRouter()


@router.get("/")
async def get_parties(
    current_user: dict | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List all non-closed parties. Public."""
    viewer_id = str(current_user["sub"]) if current_user else None
    return [party_to_dict(p, viewer_id) for p in await list_active_parties(session)]


@router.get("/{party_id}")
async def get_party_endpoint(
    party_id: str,
    current_user: dict | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return a single party by ID. Public."""
    party = await require_party(party_id, session)
    viewer_id = str(current_user["sub"]) if current_user else None
    return party_to_dict(party, viewer_id)


@router.post("/", status_code=201)
async def create_new_party(
    body: CreatePartyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Create a party. The creator is automatically added as leader/first member."""
    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")
    rsn = await get_rsn(int(current_user["sub"]), session, body.rsn_override)

    party = await create_party(
        session,
        leader_id=uid,
        leader_username=username,
        leader_rsn=rsn,
        activity=body.activity.strip(),
        description=body.description.strip() if body.description else None,
        vibe=body.vibe,
        max_size=body.max_size,
        scheduled_at=resolve_scheduled_at(body.scheduled_at) if body.scheduled_at else None,
        ttl_hours=body.ttl_hours,
        notification_category_ids=body.notification_category_ids,
    )

    message_id = await post_party_embed(party)
    if message_id:
        party.discord_message_id = message_id
        await session.commit()

    await dispatch_party_notifications(session, valkey, party)
    return party_to_dict(party, uid)


@router.patch("/{party_id}")
async def update_party(
    party_id: str,
    body: UpdatePartyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Edit party details. Leader only."""
    party = await require_party(party_id, session)
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
        _recalc_status(party)
    if body.scheduled_at is not None:
        party.scheduled_at = resolve_scheduled_at(body.scheduled_at)
    if body.notification_category_ids is not None:
        party.notification_category_ids = body.notification_category_ids

    await session.commit()
    await edit_party_embed(party)

    all_member_ids = [m.user_id for m in party.members]
    await notify(valkey, all_member_ids, f"**{party.activity}** has been updated by the party leader.")
    return party_to_dict(party, uid)


@router.delete("/{party_id}")
async def close_party_endpoint(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Close a party. Leader or staff only."""
    party = await require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")
    if party.leader_id != uid:
        if not await is_staff(int(current_user["sub"]), session):
            raise HTTPException(403, "Only the party leader or staff can close this party")

    await close_party(session, party)
    await close_party_embed(party)
    return party_to_dict(party, uid)
