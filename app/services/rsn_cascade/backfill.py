from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CofferEvent, Event, MembershipEvent, Ticket, User


async def backfill_event_user_account(
    session: AsyncSession, user_account_id: int, rsns: list[str]
) -> None:
    """Set user_account_id on all three event tables for every RSN in rsns. Does not commit."""
    lower_rsns = [r.lower() for r in rsns]
    await session.execute(
        update(Event)
        .where(
            func.replace(func.lower(Event.player_name), "\xa0", " ").in_(lower_rsns),
            Event.user_account_id.is_(None),
        )
        .values(user_account_id=user_account_id)
    )
    await session.execute(
        update(CofferEvent)
        .where(
            func.lower(CofferEvent.player_name).in_(lower_rsns),
            CofferEvent.user_account_id.is_(None),
        )
        .values(user_account_id=user_account_id)
    )
    await session.execute(
        update(MembershipEvent)
        .where(
            func.lower(MembershipEvent.player_name).in_(lower_rsns),
            MembershipEvent.user_account_id.is_(None),
        )
        .values(user_account_id=user_account_id)
    )


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
    """Fill missing stats from historical events and update User. Does NOT commit."""
    backfill: dict = {}

    if not clan_rank:
        rank_result = await session.execute(
            select(Event.data["rank"].as_string())
            .where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.data["rank"].as_string().isnot(None),
                Event.type.in_(
                    [
                        "loot",
                        "level",
                        "xp_milestone",
                        "quest",
                        "diary",
                        "combat_achievement",
                    ]
                ),
            )
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
        rank_val = rank_result.scalar_one_or_none()
        if rank_val:
            backfill["clan_rank"] = rank_val

    if not total_loot_value:
        loot_result = await session.execute(
            select(
                func.coalesce(func.sum(Event.data["coin_value"].as_integer()), 0)
            ).where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.type.in_(["loot", "loot_key", "clue_item"]),
            )
        )
        total_loot = loot_result.scalar_one_or_none() or 0
        if total_loot:
            backfill["total_loot_value"] = total_loot

    if not collection_log_slots:
        cl_result = await session.execute(
            select(
                func.coalesce(func.max(Event.data["log_slots"].as_integer()), 0)
            ).where(
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
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(**backfill)
        )

    return backfill
