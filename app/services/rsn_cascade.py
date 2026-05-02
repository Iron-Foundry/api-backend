from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CofferEvent, Event, Leaderboard, MembershipEvent, Ticket, User


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


async def get_user_ticket_ids(session: AsyncSession, discord_user_id: int) -> list[int]:
    """Return sorted list of ticket IDs created by this user."""
    result = await session.execute(
        select(Ticket.ticket_id).where(Ticket.creator_id == discord_user_id)
    )
    return sorted([row[0] for row in result])


async def backfill_user_from_rsn(
    session: AsyncSession,
    discord_user_id: int,
    rsn: str,
    *,
    clan_rank: str | None = None,
    total_loot_value: int = 0,
    collection_log_slots: int = 0,
) -> dict:
    """Fill missing stats from historical events and update User. Does NOT commit.

    Returns the dict of fields that were backfilled.
    """
    backfill: dict = {}

    if not clan_rank:
        rank_result = await session.execute(
            select(Event.data["rank"].as_string())
            .where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.data["rank"].as_string().isnot(None),
                Event.type.in_(["loot", "level", "xp_milestone", "quest", "diary", "combat_achievement"]),
            )
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
        rank_val = rank_result.scalar_one_or_none()
        if rank_val:
            backfill["clan_rank"] = rank_val

    if not total_loot_value:
        loot_result = await session.execute(
            select(func.coalesce(func.sum(Event.data["coin_value"].as_integer()), 0)).where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.type.in_(["loot", "loot_key", "clue_item"]),
            )
        )
        total_loot = loot_result.scalar_one_or_none() or 0
        if total_loot:
            backfill["total_loot_value"] = total_loot

    if not collection_log_slots:
        cl_result = await session.execute(
            select(func.coalesce(func.max(Event.data["log_slots"].as_integer()), 0)).where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.type == "collection_log",
            )
        )
        cl_slots = cl_result.scalar_one_or_none() or 0
        if cl_slots:
            backfill["collection_log_slots"] = cl_slots

    ticket_ids = await get_user_ticket_ids(session, discord_user_id)
    if ticket_ids:
        backfill["ticket_ids"] = ticket_ids

    if backfill:
        backfill["updated_at"] = datetime.now(timezone.utc)
        await session.execute(
            update(User).where(User.discord_user_id == discord_user_id).values(**backfill)
        )

    return backfill
