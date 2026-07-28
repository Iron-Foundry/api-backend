from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import PartyDB, PartyNotificationPreferences, User, UserAccount
from app.party_store import Vibe, get_party
from app.services.page_permissions import get_admin_bypass_roles
from app.services.rank_mappings import get_effective_roles

_NOTIFY_CHANNEL = "foundry:party_notify"
_SITE_URL = (
    os.getenv("FRONTEND_URL", "https://ironfoundry.cc")
    .split(",")[0]
    .strip()
    .rstrip("/")
)
_VIBE_COLOR = {"learning": 0x5865F2, "chill": 0x57F287, "sweat": 0xED4245}
_VIBE_LABEL = {"learning": "Learning", "chill": "Chill", "sweat": "Sweat"}


class CreatePartyRequest(BaseModel):
    activity: Annotated[
        str, Field(min_length=1, max_length=60, examples=["Chambers of Xeric"])
    ]
    description: Annotated[
        str | None,
        Field(max_length=300, examples=["Learner runs, bring your own supplies."]),
    ] = None
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


class UpdateNotificationPrefsRequest(BaseModel):
    category_ids: list[str] = []


async def require_party(party_id: str, session: AsyncSession) -> PartyDB:
    party = await get_party(session, party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    return party


async def is_staff(uid: int, session: AsyncSession) -> bool:
    roles = await get_effective_roles(uid, session)
    bypass = await get_admin_bypass_roles(session)
    return bool(bypass and any(r in bypass for r in roles))


async def get_rsn(
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


def resolve_scheduled_at(dt: datetime) -> datetime:
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if dt > now:
        return dt
    today = now.date()
    candidate = datetime(
        today.year, today.month, today.day, dt.hour, dt.minute, tzinfo=UTC
    )
    if candidate > now:
        return candidate
    return now + timedelta(hours=1)


async def notify(valkey: Valkey, user_ids: list[str], message: str) -> None:
    if not user_ids or not message:
        return
    await valkey.publish(
        _NOTIFY_CHANNEL, json.dumps({"user_ids": user_ids, "message": message})
    )


async def dispatch_party_notifications(
    session: AsyncSession, valkey: Valkey, party: PartyDB
) -> None:
    """DM opted-in users when a party is created, excluding the leader."""
    if not party.notification_category_ids:
        return

    result = await session.execute(select(PartyNotificationPreferences))
    all_prefs = result.scalars().all()

    cat_set = set(party.notification_category_ids)
    leader_id = int(party.leader_id)
    user_ids = [
        str(pref.user_id)
        for pref in all_prefs
        if pref.user_id != leader_id and bool(cat_set & set(pref.category_ids or []))
    ]
    if not user_ids:
        return

    leader_name = party.leader_rsn or party.leader_username
    fields = [
        {"name": "Leader", "value": leader_name, "inline": True},
        {
            "name": "Vibe",
            "value": _VIBE_LABEL.get(party.vibe, party.vibe.capitalize()),
            "inline": True,
        },
        {
            "name": "Size",
            "value": f"{len(party.members)}/{party.max_size}",
            "inline": True,
        },
    ]
    if party.scheduled_at:
        ts = int(party.scheduled_at.timestamp())
        fields.append({"name": "Scheduled", "value": f"<t:{ts}:f>", "inline": False})

    expires_ts = int(party.expires_at.timestamp())
    fields.append({"name": "Expires", "value": f"<t:{expires_ts}:R>", "inline": False})

    embed: dict[str, Any] = {
        "title": f"New Party: {party.activity}",
        "color": _VIBE_COLOR.get(party.vibe, 0x57F287),
        "fields": fields,
        "url": f"{_SITE_URL}/parties",
    }
    if party.description:
        embed["description"] = party.description

    await valkey.publish(
        _NOTIFY_CHANNEL, json.dumps({"user_ids": user_ids, "embed": embed})
    )
