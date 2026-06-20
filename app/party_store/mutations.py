from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartyChatMessageDB, PartyDB, PartyMemberDB

from ._constants import Vibe, _generate_hub_code


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
    notification_category_ids: list[str],
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
        notification_category_ids=notification_category_ids,
        hub_code=_generate_hub_code(),
        status="open",
        created_at=now,
        scheduled_at=scheduled_at,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    session.add(party)
    session.add(
        PartyMemberDB(
            id=str(uuid.uuid4()),
            party_id=party_id,
            user_id=leader_id,
            username=leader_username,
            rsn=leader_rsn,
            joined_at=now,
        )
    )
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
    session.add(
        PartyMemberDB(
            id=str(uuid.uuid4()),
            party_id=party.id,
            user_id=user_id,
            username=username,
            rsn=rsn,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()
    await session.refresh(party, attribute_names=["members"])
    _recalc_status(party)
    await session.commit()


async def remove_member(session: AsyncSession, party: PartyDB, user_id: str) -> bool:
    result = cast(
        CursorResult,
        await session.execute(
            delete(PartyMemberDB).where(
                PartyMemberDB.party_id == party.id, PartyMemberDB.user_id == user_id
            )
        ),
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
