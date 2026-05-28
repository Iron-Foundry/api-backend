"""Parties router - DB-backed party management."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from valkey.asyncio import Valkey

from sqlalchemy import func, select

from app.db.models import PartyChatMessageDB, PartyDB, PartyNotificationPreferences, User, UserAccount
from app.dependencies import get_current_user, get_optional_user, get_session, get_valkey
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

_NOTIFY_CHANNEL = "foundry:party_notify"
_SITE_URL = os.getenv("FRONTEND_URL", "https://ironfoundry.cc").split(",")[0].strip().rstrip("/")


async def _notify(valkey: Valkey, user_ids: list[str], message: str) -> None:
    if not user_ids or not message:
        return
    await valkey.publish(
        _NOTIFY_CHANNEL, json.dumps({"user_ids": user_ids, "message": message})
    )


_VIBE_COLOR = {"learning": 0x5865F2, "chill": 0x57F287, "sweat": 0xED4245}
_VIBE_LABEL = {"learning": "Learning", "chill": "Chill", "sweat": "Sweat"}


async def _dispatch_party_notifications(
    session: AsyncSession,
    valkey: Valkey,
    party: object,
) -> None:
    """DM opted-in users when a party is created, excluding the leader."""
    p: PartyDB = party  # type: ignore[assignment]
    if not p.notification_category_ids:
        return

    result = await session.execute(select(PartyNotificationPreferences))
    all_prefs = result.scalars().all()

    cat_set = set(p.notification_category_ids)
    leader_id = int(p.leader_id)
    user_ids = [
        str(pref.user_id)
        for pref in all_prefs
        if pref.user_id != leader_id and bool(cat_set & set(pref.category_ids or []))
    ]
    if not user_ids:
        return

    leader_name = p.leader_rsn or p.leader_username
    fields = [
        {"name": "Leader", "value": leader_name, "inline": True},
        {"name": "Vibe", "value": _VIBE_LABEL.get(p.vibe, p.vibe.capitalize()), "inline": True},
        {"name": "Size", "value": f"{len(p.members)}/{p.max_size}", "inline": True},
    ]
    if p.scheduled_at:
        ts = int(p.scheduled_at.timestamp())
        fields.append({"name": "Scheduled", "value": f"<t:{ts}:f>", "inline": False})

    expires_ts = int(p.expires_at.timestamp())
    fields.append({"name": "Expires", "value": f"<t:{expires_ts}:R>", "inline": False})

    embed: dict = {
        "title": f"New Party: {p.activity}",
        "color": _VIBE_COLOR.get(p.vibe, 0x57F287),
        "fields": fields,
        "url": f"{_SITE_URL}/parties",
    }
    if p.description:
        embed["description"] = p.description

    await valkey.publish(
        _NOTIFY_CHANNEL, json.dumps({"user_ids": user_ids, "embed": embed})
    )


# ── Request models ────────────────────────────────────────────────────────────


class CreatePartyRequest(BaseModel):
    activity: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str | None, Field(max_length=300)] = None
    vibe: Vibe = "chill"
    max_size: Annotated[int, Field(ge=1, le=100)]
    scheduled_at: datetime | None = None
    ttl_hours: Annotated[float, Field(ge=0.5, le=24)] = 4.0
    notification_category_ids: list[str] = []
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
    notification_category_ids: list[str] | None = None

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
    valkey: Valkey = Depends(get_valkey),
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
        notification_category_ids=body.notification_category_ids,
    )

    message_id = await post_party_embed(party)
    if message_id:
        party.discord_message_id = message_id
        await session.commit()

    await _dispatch_party_notifications(session, valkey, party)
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
    if body.notification_category_ids is not None:
        party.notification_category_ids = body.notification_category_ids

    await session.commit()
    await edit_party_embed(party)

    all_member_ids = [m.user_id for m in party.members]
    await _notify(
        valkey,
        all_member_ids,
        f"**{party.activity}** has been updated by the party leader.",
    )
    return party_to_dict(party, uid)


@router.post("/{party_id}/join")
async def join_party(
    party_id: str,
    body: JoinPartyRequest = Body(default_factory=JoinPartyRequest),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
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

    existing_ids = [m.user_id for m in party.members]
    username = current_user.get("username", "Unknown")
    rsn = await _get_rsn(int(current_user["sub"]), session, body.rsn_override)
    await add_member(session, party, user_id=uid, username=username, rsn=rsn)
    await edit_party_embed(party)

    joiner_name = rsn or username
    await _notify(
        valkey,
        existing_ids,
        f"**{joiner_name}** joined **{party.activity}**.\n"
        f"Spots: {len(party.members)}/{party.max_size}",
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
    party = await _require_party(party_id, session)
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
    await _notify(
        valkey,
        remaining_ids,
        f"**{leaving_name}** left **{party.activity}**.\n"
        f"Spots: {len(party.members)}/{party.max_size}",
    )
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
    valkey: Valkey = Depends(get_valkey),
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

    kicked_member = next((m for m in party.members if m.user_id == target_user_id), None)
    kicked_name = (
        (kicked_member.rsn or kicked_member.username) if kicked_member else "A member"
    )
    if not await remove_member(session, party, target_user_id):
        raise HTTPException(404, "Member not found in this party")

    await edit_party_embed(party)

    remaining_ids = [m.user_id for m in party.members]
    await _notify(
        valkey,
        [target_user_id],
        f"You were removed from **{party.activity}** by the party leader.",
    )
    await _notify(
        valkey,
        remaining_ids,
        f"**{kicked_name}** was removed from **{party.activity}** by the leader.",
    )
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


@router.get("/notifications")
async def get_notification_preferences(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the current user's party notification preferences."""
    uid = int(current_user["sub"])
    result = await session.execute(
        select(PartyNotificationPreferences).where(
            PartyNotificationPreferences.user_id == uid
        )
    )
    prefs = result.scalar_one_or_none()
    return {"category_ids": prefs.category_ids if prefs else []}


class UpdateNotificationPrefsRequest(BaseModel):
    category_ids: list[str] = []


@router.put("/notifications")
async def update_notification_preferences(
    body: UpdateNotificationPrefsRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upsert the current user's party notification preferences."""
    uid = int(current_user["sub"])
    stmt = (
        pg_insert(PartyNotificationPreferences)
        .values(user_id=uid, category_ids=body.category_ids)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"category_ids": body.category_ids},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return {"category_ids": body.category_ids}


@router.post("/{party_id}/chat", status_code=201)
async def send_chat(
    party_id: str,
    body: SendChatRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Post a chat message to a party."""
    party = await _require_party(party_id, session)
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
        await _notify(
            valkey,
            others,
            f"**{username}** sent their first message in **{party.activity}** party chat!\n"
            f"ironfoundry.cc/parties/{party_id}",
        )

    return chat_message_to_dict(msg)
