from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CofferEvent, Event, Leaderboard, MembershipEvent, User


async def cascade_rsn_change(session: AsyncSession, old_rsn: str, new_rsn: str) -> None:
    """Rename player_name across all PG tables when a user changes their RSN.

    Commits the transaction internally.
    """
    now = datetime.now(timezone.utc)

    await session.execute(
        update(User).where(User.rsn == old_rsn).values(rsn=new_rsn, updated_at=now)
    )

    await session.execute(
        update(Event)
        .where(func.lower(Event.player_name) == old_rsn.lower())
        .values(player_name=new_rsn)
    )

    await session.execute(
        text(
            "UPDATE events SET data = jsonb_set(data, '{winner}', to_jsonb(CAST(:new_rsn AS text)))"
            " WHERE type = 'pk' AND lower(data->>'winner') = lower(:old_rsn)"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        text(
            "UPDATE events SET data = jsonb_set(data, '{loser}', to_jsonb(CAST(:new_rsn AS text)))"
            " WHERE type = 'pk' AND lower(data->>'loser') = lower(:old_rsn)"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )

    await session.execute(
        update(CofferEvent)
        .where(func.lower(CofferEvent.player_name) == old_rsn.lower())
        .values(player_name=new_rsn)
    )

    await session.execute(
        update(MembershipEvent)
        .where(func.lower(MembershipEvent.player_name) == old_rsn.lower())
        .values(player_name=new_rsn)
    )

    await session.execute(
        update(Leaderboard)
        .where(func.lower(Leaderboard.player_name) == old_rsn.lower())
        .values(player_name=new_rsn)
    )

    await session.commit()
