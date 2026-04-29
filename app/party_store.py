"""In-memory party store — parties reset on restart (by design)."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

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

Vibe = Literal["learning", "chill", "sweat"]

VIBE_EMOJI: dict[str, str] = {
    "learning": "🎓",
    "chill":    "😌",
    "sweat":    "💪",
}

VIBE_COLOUR: dict[str, int] = {
    "learning": 0x5865F2,  # blurple
    "chill":    0x57F287,  # green
    "sweat":    0xED4245,  # red
}


@dataclass
class PartyMember:
    user_id: str
    username: str
    rsn: str | None
    joined_at: datetime


@dataclass
class ChatMessage:
    id: str
    user_id: str
    username: str
    rsn: str | None
    text: str
    sent_at: datetime


@dataclass
class Party:
    id: str
    leader_id: str
    leader_username: str
    leader_rsn: str | None
    activity: str
    description: str | None
    vibe: Vibe
    max_size: int
    members: list[PartyMember] = field(default_factory=list)
    chat: list[ChatMessage] = field(default_factory=list)
    ping_role_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: datetime | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["open", "full", "closed"] = "open"
    discord_message_id: str | None = None
    hub_code: str = field(default_factory=_generate_hub_code)


# ── Store ─────────────────────────────────────────────────────────────────────

_parties: dict[str, Party] = {}


# ── Mutators ──────────────────────────────────────────────────────────────────

def create_party(
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
) -> Party:
    now = datetime.now(timezone.utc)
    party = Party(
        id=str(uuid.uuid4()),
        leader_id=leader_id,
        leader_username=leader_username,
        leader_rsn=leader_rsn,
        activity=activity,
        description=description,
        vibe=vibe,
        max_size=max_size,
        members=[PartyMember(user_id=leader_id, username=leader_username, rsn=leader_rsn, joined_at=now)],
        ping_role_ids=ping_role_ids,
        created_at=now,
        scheduled_at=scheduled_at,
        expires_at=now + timedelta(hours=ttl_hours),
        status="open",
    )
    _parties[party.id] = party
    return party


def _recalc_status(party: Party) -> None:
    if party.status == "closed":
        return
    party.status = "full" if len(party.members) >= party.max_size else "open"


def add_member(party: Party, *, user_id: str, username: str, rsn: str | None) -> None:
    party.members.append(PartyMember(user_id=user_id, username=username, rsn=rsn, joined_at=datetime.now(timezone.utc)))
    _recalc_status(party)


def remove_member(party: Party, user_id: str) -> bool:
    before = len(party.members)
    party.members = [m for m in party.members if m.user_id != user_id]
    if len(party.members) < before:
        _recalc_status(party)
        return True
    return False


def add_chat_message(party: Party, *, user_id: str, username: str, rsn: str | None, text: str) -> ChatMessage:
    msg = ChatMessage(id=str(uuid.uuid4()), user_id=user_id, username=username, rsn=rsn, text=text, sent_at=datetime.now(timezone.utc))
    party.chat.append(msg)
    if len(party.chat) > 200:
        party.chat = party.chat[-200:]
    return msg


def close_party(party: Party) -> None:
    party.status = "closed"


def expire_parties() -> list[Party]:
    """Mark timed-out parties as closed and return the newly-expired list."""
    now = datetime.now(timezone.utc)
    expired = []
    for party in list(_parties.values()):
        if party.status != "closed" and party.expires_at <= now:
            party.status = "closed"
            expired.append(party)
    return expired


# ── Queries ───────────────────────────────────────────────────────────────────

def get_party(party_id: str) -> Party | None:
    return _parties.get(party_id)


def list_active_parties() -> list[Party]:
    return [p for p in _parties.values() if p.status != "closed"]


# ── Serialisers ───────────────────────────────────────────────────────────────

def party_to_dict(party: Party, viewer_id: str | None = None) -> dict:
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
        "ping_role_ids": party.ping_role_ids,
        "status": party.status,
        "created_at": party.created_at.isoformat(),
        "scheduled_at": party.scheduled_at.isoformat() if party.scheduled_at else None,
        "expires_at": party.expires_at.isoformat(),
        "hub_code": party.hub_code if is_member else None,
    }


def chat_message_to_dict(msg: ChatMessage) -> dict:
    return {
        "id": msg.id,
        "user_id": msg.user_id,
        "username": msg.username,
        "rsn": msg.rsn,
        "text": msg.text,
        "sent_at": msg.sent_at.isoformat(),
    }
