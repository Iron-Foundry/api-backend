from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PartyChatMessageDB, PartyDB


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


async def get_chat_messages(
    session: AsyncSession, party_id: str, limit: int = 50
) -> list[PartyChatMessageDB]:
    result = await session.execute(
        select(PartyChatMessageDB)
        .where(PartyChatMessageDB.party_id == party_id)
        .order_by(PartyChatMessageDB.sent_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def expire_parties(session: AsyncSession) -> list[PartyDB]:
    """Mark timed-out parties as closed and return the newly-expired list."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    result = await session.execute(
        _with_members(
            select(PartyDB).where(PartyDB.status != "closed", PartyDB.expires_at <= now)
        )
    )
    parties = list(result.scalars().all())
    for party in parties:
        party.status = "closed"
    if parties:
        await session.commit()
    return parties
