"""Parties router - DB-backed party management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func, select

from app.db.models import User, UserAccount
from app.dependencies import get_current_user, get_optional_user, get_session
from app.party_store import (
    Vibe,
    _recalc_status,
    add_chat_message,
    add_member,
    chat_message_to_dict,
    close_party,
    create_party,
    get_chat_messages,
    get_party,
    list_active_parties,
    party_to_dict,
    remove_member,
)
from app.services.discord_party import (
    close_party_embed,
    edit_party_embed,
    post_party_embed,
)
from app.services.page_permissions import get_admin_bypass_roles
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/parties", tags=["parties"])


# ── Request models ────────────────────────────────────────────────────────────


class CreatePartyRequest(BaseModel):
    activity: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str | None, Field(max_length=300)] = None
    vibe: Vibe = "chill"
    max_size: Annotated[int, Field(ge=1, le=100)]
    scheduled_at: datetime | None = None
    ttl_hours: Annotated[float, Field(ge=0.5, le=24)] = 4.0
    ping_role_ids: list[str] = []
    rsn_override: str | None = None

    @field_validator("activity")
    @classmethod
    def activity_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("activity must not be blank")
        return v

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v


class UpdatePartyRequest(BaseModel):
    activity: Annotated[str | None, Field(min_length=1, max_length=60)] = None
    description: Annotated[str | None, Field(max_length=300)] = None
    vibe: Vibe | None = None
    max_size: Annotated[int | None, Field(ge=1, le=100)] = None
    scheduled_at: datetime | None = None
    ping_role_ids: list[str] | None = None

    @field_validator("activity")
    @classmethod
    def activity_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("activity must not be blank")
        return v


class JoinPartyRequest(BaseModel):
    rsn_override: str | None = None


class SendChatRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=300)]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _require_party(party_id: str, session: AsyncSession):  # type: ignore[return]
    party = await get_party(session, party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    return party


async def _is_staff(uid: int, session: AsyncSession) -> bool:
    roles = await get_effective_roles(uid, session)
    bypass = await get_admin_bypass_roles(session)
    return bool(bypass and any(r in bypass for r in roles))


async def _get_rsn(
    uid: int, session: AsyncSession, rsn_override: str | None = None
) -> str | None:
    if rsn_override:
        result = await session.execute(
            select(UserAccount.rsn).where(
                UserAccount.discord_user_id == uid,
                func.lower(UserAccount.rsn) == rsn_override.lower(),
            )
        )
        return result.scalar_one_or_none()
    result = await session.execute(select(User.rsn).where(User.discord_user_id == uid))
    return result.scalar_one_or_none()


def _resolve_scheduled_at(dt: datetime) -> datetime:
    """Ensure scheduled_at is in the future.

    - Past date → replace with today's date at the same time.
    - Still in the past → now + 1 hour.
    """
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt > now:
        return dt
    today = now.date()
    candidate = datetime(
        today.year, today.month, today.day, dt.hour, dt.minute, tzinfo=timezone.utc
    )
    if candidate > now:
        return candidate
    return now + timedelta(hours=1)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
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
    party = await _require_party(party_id, session)
    viewer_id = str(current_user["sub"]) if current_user else None
    return party_to_dict(party, viewer_id)


@router.post("", status_code=201)
async def create_new_party(
    body: CreatePartyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a party. The creator is automatically added as leader/first member."""
    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")
    rsn = await _get_rsn(int(current_user["sub"]), session, body.rsn_override)

    party = await create_party(
        session,
        leader_id=uid,
        leader_username=username,
        leader_rsn=rsn,
        activity=body.activity.strip(),
        description=body.description.strip() if body.description else None,
        vibe=body.vibe,
        max_size=body.max_size,
        scheduled_at=_resolve_scheduled_at(body.scheduled_at)
        if body.scheduled_at
        else None,
        ttl_hours=body.ttl_hours,
        ping_role_ids=body.ping_role_ids,
    )

    message_id = await post_party_embed(party)
    if message_id:
        party.discord_message_id = message_id
        await session.commit()

    return party_to_dict(party, uid)


@router.patch("/{party_id}")
async def update_party(
    party_id: str,
    body: UpdatePartyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Edit party details. Leader only."""
    party = await _require_party(party_id, session)
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
        party.scheduled_at = _resolve_scheduled_at(body.scheduled_at)
    if body.ping_role_ids is not None:
        party.ping_role_ids = body.ping_role_ids

    await session.commit()
    await edit_party_embed(party)
    return party_to_dict(party, uid)


@router.post("/{party_id}/join")
async def join_party(
    party_id: str,
    body: JoinPartyRequest = Body(default_factory=JoinPartyRequest),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Join an open party."""
    party = await _require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is closed")
    if party.status == "full":
        raise HTTPException(409, "Party is full")
    if any(m.user_id == uid for m in party.members):
        raise HTTPException(409, "Already in this party")

    username = current_user.get("username", "Unknown")
    rsn = await _get_rsn(int(current_user["sub"]), session, body.rsn_override)
    await add_member(session, party, user_id=uid, username=username, rsn=rsn)
    await edit_party_embed(party)
    return party_to_dict(party, uid)


@router.delete("/{party_id}/leave")
async def leave_party(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Leave a party. Leaders cannot leave - they must close the party instead."""
    party = await _require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.leader_id == uid:
        raise HTTPException(400, "Leaders cannot leave - close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")
    if not await remove_member(session, party, uid):
        raise HTTPException(404, "You are not in this party")

    await edit_party_embed(party)
    return party_to_dict(party, uid)


@router.delete("/{party_id}")
async def close_party_endpoint(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Close a party. Leader or staff only."""
    party = await _require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.status == "closed":
        raise HTTPException(409, "Party is already closed")
    if party.leader_id != uid:
        if not await _is_staff(int(current_user["sub"]), session):
            raise HTTPException(
                403, "Only the party leader or staff can close this party"
            )

    await close_party(session, party)
    await close_party_embed(party)
    return party_to_dict(party, uid)


@router.delete("/{party_id}/members/{target_user_id}")
async def kick_member(
    party_id: str,
    target_user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Kick a member from the party. Leader only."""
    party = await _require_party(party_id, session)
    uid = str(current_user["sub"])

    if party.leader_id != uid:
        raise HTTPException(403, "Only the party leader can kick members")
    if target_user_id == uid:
        raise HTTPException(400, "Cannot kick yourself - close the party instead")
    if party.status == "closed":
        raise HTTPException(409, "Party is closed")
    if not await remove_member(session, party, target_user_id):
        raise HTTPException(404, "Member not found in this party")

    await edit_party_embed(party)
    return party_to_dict(party, uid)


@router.get("/{party_id}/chat")
async def get_chat(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Fetch the most recent 50 chat messages for a party."""
    party = await _require_party(party_id, session)
    _ = party  # existence check only
    messages = await get_chat_messages(session, party_id)
    return [chat_message_to_dict(m) for m in messages]


@router.post("/{party_id}/chat", status_code=201)
async def send_chat(
    party_id: str,
    body: SendChatRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Post a chat message to a party."""
    party = await _require_party(party_id, session)
    if party.status == "closed":
        raise HTTPException(409, "Cannot chat in a closed party")

    uid = str(current_user["sub"])
    username = current_user.get("username", "Unknown")
    msg = await add_chat_message(
        session,
        party_id,
        user_id=uid,
        username=username,
        rsn=None,
        text=body.text.strip(),
    )
    return chat_message_to_dict(msg)
