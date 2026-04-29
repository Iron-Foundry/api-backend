"""Party store - DB-backed async operations."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PartyChatMessageDB, PartyDB, PartyMemberDB

if TYPE_CHECKING:
    pass

Vibe = Literal["learning", "chill", "sweat"]

VIBE_EMOJI: dict[str, str] = {
    "learning": "🎓",
    "chill":    "😌",
    "sweat":    "💪",
}

VIBE_COLOUR: dict[str, int] = {
    "learning": 0x5865F2,
    "chill":    0x57F287,
    "sweat":    0xED4245,
}

_WORDLIST = [
    "abyssal","ancient","anvil","arcane","armadyl","arrow","axe",
    "bandos","barrows","berserker","brimstone","bronze","brutal",
    "cannonball","chaos","chimera","coffer","coral","crystal",
    "dagannoth","dark","death","defender","demon","divine","dragon",
    "dragonfire","dusk","dwarf","elder","eternal","fighter","fire",
    "flask","forest","fury","ghost","giant","gloves","goblin",
    "golem","granite","guthix","hammer","helm","hunter","hydra",
    "infernal","iron","jad","justiciar","karambwan","kraken","lance",
    "lava","lobster","magic","manta","maple","marble","master",
    "monk","mortar","mud","mystic","nature","needle","nex",
    "nightmare","oak","obsidian","onyx","oracle","pegasian","pickaxe",
    "prayer","quartz","quest","ranger","rapier","rune","sacred",
    "saradomin","scimitar","seed","shark","shield","silver","skeleton",
    "slayer","smoke","snow","soul","spade","spectral","staff","steel",
    "storm","sword","teak","thorn","titan","toad","tome","torch",
    "torva","toxic","trident","tuna","twisted","vanguard","venom",
    "vigour","viper","void","vorkath","warhammer","warped","water",
    "whip","willow","wings","witch","wolf","wrath","yew",
    "zamorak","zenyte","zulrah",
]


def _generate_hub_code() -> str:
    return "-".join(random.choices(_WORDLIST, k=3))


# ── Queries ───────────────────────────────────────────────────────────────────

def _with_members(q):
    return q.options(selectinload(PartyDB.members))


async def get_party(session: AsyncSession, party_id: str) -> PartyDB | None:
    result = await session.execute(
        _with_members(select(PartyDB).where(PartyDB.id == party_id))
    )
    return result.scalar_one_or_none()


async def list_active_parties(session: AsyncSession) -> list[PartyDB]:
    result = await session.execute(
        _with_members(
            select(PartyDB)
            .where(PartyDB.status != "closed")
            .order_by(PartyDB.created_at.desc())
        )
    )
    return list(result.scalars().all())


# ── Mutators ──────────────────────────────────────────────────────────────────

def _recalc_status(party: PartyDB) -> None:
    if party.status == "closed":
        return
    party.status = "full" if len(party.members) >= party.max_size else "open"


async def create_party(
    session: AsyncSession,
    *,
    leader_id: str,
    leader_username: str,
    leader_rsn: str | None,
    activity: str,
    description: str | None,
    vibe: Vibe,
    max_size: int,
    scheduled_at: datetime | None,
    ttl_hours: float,
    ping_role_ids: list[str],
) -> PartyDB:
    now = datetime.now(timezone.utc)
    party_id = str(uuid.uuid4())
    party = PartyDB(
        id=party_id,
        leader_id=leader_id,
        leader_username=leader_username,
        leader_rsn=leader_rsn,
        activity=activity,
        description=description,
        vibe=vibe,
        max_size=max_size,
        ping_role_ids=ping_role_ids,
        hub_code=_generate_hub_code(),
        status="open",
        created_at=now,
        scheduled_at=scheduled_at,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    member = PartyMemberDB(
        id=str(uuid.uuid4()),
        party_id=party_id,
        user_id=leader_id,
        username=leader_username,
        rsn=leader_rsn,
        joined_at=now,
    )
    session.add(party)
    session.add(member)
    await session.commit()
    await session.refresh(party, attribute_names=["members"])
    return party


async def add_member(
    session: AsyncSession,
    party: PartyDB,
    *,
    user_id: str,
    username: str,
    rsn: str | None,
) -> None:
    member = PartyMemberDB(
        id=str(uuid.uuid4()),
        party_id=party.id,
        user_id=user_id,
        username=username,
        rsn=rsn,
        joined_at=datetime.now(timezone.utc),
    )
    session.add(member)
    await session.flush()
    await session.refresh(party, attribute_names=["members"])
    _recalc_status(party)
    await session.commit()


async def remove_member(session: AsyncSession, party: PartyDB, user_id: str) -> bool:
    result = await session.execute(
        delete(PartyMemberDB)
        .where(PartyMemberDB.party_id == party.id, PartyMemberDB.user_id == user_id)
    )
    if result.rowcount == 0:
        return False
    await session.flush()
    await session.refresh(party, attribute_names=["members"])
    _recalc_status(party)
    await session.commit()
    return True


async def close_party(session: AsyncSession, party: PartyDB) -> None:
    party.status = "closed"
    await session.commit()


async def add_chat_message(
    session: AsyncSession,
    party_id: str,
    *,
    user_id: str,
    username: str,
    rsn: str | None,
    text: str,
) -> PartyChatMessageDB:
    msg = PartyChatMessageDB(
        id=str(uuid.uuid4()),
        party_id=party_id,
        user_id=user_id,
        username=username,
        rsn=rsn,
        text=text,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(msg)
    await session.commit()
    return msg


async def get_chat_messages(session: AsyncSession, party_id: str, limit: int = 50) -> list[PartyChatMessageDB]:
    result = await session.execute(
        select(PartyChatMessageDB)
        .where(PartyChatMessageDB.party_id == party_id)
        .order_by(PartyChatMessageDB.sent_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def expire_parties(session: AsyncSession) -> list[PartyDB]:
    """Mark timed-out parties as closed and return the newly-expired list."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        _with_members(
            select(PartyDB)
            .where(PartyDB.status != "closed", PartyDB.expires_at <= now)
        )
    )
    parties = list(result.scalars().all())
    for party in parties:
        party.status = "closed"
    if parties:
        await session.commit()
    return parties


# ── Serialisers ───────────────────────────────────────────────────────────────

def party_to_dict(party: PartyDB, viewer_id: str | None = None) -> dict:
    is_member = viewer_id is not None and any(m.user_id == viewer_id for m in party.members)
    return {
        "id": party.id,
        "activity": party.activity,
        "description": party.description,
        "vibe": party.vibe,
        "leader": {
            "user_id": party.leader_id,
            "username": party.leader_username,
            "rsn": party.leader_rsn,
        },
        "max_size": party.max_size,
        "member_count": len(party.members),
        "members": [
            {"user_id": m.user_id, "username": m.username, "rsn": m.rsn, "joined_at": m.joined_at.isoformat()}
            for m in party.members
        ],
        "ping_role_ids": party.ping_role_ids or [],
        "status": party.status,
        "created_at": party.created_at.isoformat(),
        "scheduled_at": party.scheduled_at.isoformat() if party.scheduled_at else None,
        "expires_at": party.expires_at.isoformat(),
        "hub_code": party.hub_code if is_member else None,
    }


def chat_message_to_dict(msg: PartyChatMessageDB) -> dict:
    return {
        "id": msg.id,
        "user_id": msg.user_id,
        "username": msg.username,
        "rsn": msg.rsn,
        "text": msg.text,
        "sent_at": msg.sent_at.isoformat(),
    }
