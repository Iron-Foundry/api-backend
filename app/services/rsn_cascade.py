from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CofferEvent,
    Event,
    FrenzySubmission,
    Leaderboard,
    MembershipEvent,
    PartyChatMessageDB,
    PartyDB,
    PartyMemberDB,
    PlayerRanking,
    PlayerSnapshot,
    Ticket,
    User,
    UserAccount,
)


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


async def _cascade_rsn_single(
    session: AsyncSession, old_rsn: str, new_rsn: str, now: datetime
) -> None:
    """Update all data tables for one old_rsn → new_rsn substitution. Does not commit."""
    await session.execute(
        update(User)
        .where(func.lower(User.rsn) == old_rsn.lower())
        .values(rsn=new_rsn, updated_at=now)
    )

    # Leaderboard has a composite PK (player_name, activity, variant).
    # Delete old_rsn rows that would conflict with an existing new_rsn row,
    # then update the remainder.
    await session.execute(
        text(
            "DELETE FROM leaderboards"
            " WHERE lower(player_name) = lower(:old_rsn)"
            " AND EXISTS ("
            "   SELECT 1 FROM leaderboards l2"
            "   WHERE l2.player_name = :new_rsn"
            "   AND l2.activity = leaderboards.activity"
            "   AND l2.variant = leaderboards.variant"
            " )"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        update(Leaderboard)
        .where(func.lower(Leaderboard.player_name) == old_rsn.lower())
        .values(player_name=new_rsn)
    )

    # PlayerRanking has a unique constraint on rsn. RankingService may have already
    # written new_rsn before the cascade runs. Ensure new_rsn exists (copying old row
    # if absent), then delete the stale old_rsn row unconditionally.
    await session.execute(
        text(
            "INSERT INTO player_rankings (rsn, rank, points, boss_points, skill_points, discord_user_id, updated_at)"
            " SELECT :new_rsn, rank, points, boss_points, skill_points, discord_user_id, updated_at"
            " FROM player_rankings WHERE lower(rsn) = lower(:old_rsn)"
            " ON CONFLICT (rsn) DO NOTHING"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        delete(PlayerRanking).where(func.lower(PlayerRanking.rsn) == old_rsn.lower())
    )

    # Same guard for PlayerSnapshot.
    await session.execute(
        text(
            "INSERT INTO player_snapshots (rsn, skills, bosses, fetched_at)"
            " SELECT :new_rsn, skills, bosses, fetched_at"
            " FROM player_snapshots WHERE lower(rsn) = lower(:old_rsn)"
            " ON CONFLICT (rsn) DO NOTHING"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        delete(PlayerSnapshot).where(func.lower(PlayerSnapshot.rsn) == old_rsn.lower())
    )

    await session.execute(
        update(FrenzySubmission)
        .where(func.lower(FrenzySubmission.player_rsn) == old_rsn.lower())
        .values(player_rsn=new_rsn)
    )

    await session.execute(
        update(PartyDB)
        .where(func.lower(PartyDB.leader_rsn) == old_rsn.lower())
        .values(leader_rsn=new_rsn)
    )

    await session.execute(
        update(PartyMemberDB)
        .where(func.lower(PartyMemberDB.rsn) == old_rsn.lower())
        .values(rsn=new_rsn)
    )

    await session.execute(
        update(PartyChatMessageDB)
        .where(func.lower(PartyChatMessageDB.rsn) == old_rsn.lower())
        .values(rsn=new_rsn)
    )


async def cascade_rsn_change(session: AsyncSession, old_rsn: str, new_rsn: str) -> None:
    """Rename player_name across all PG tables when a user changes their RSN.

    Looks up all historical RSNs linked to the same user via user_accounts and
    cascades each one → new_rsn, ensuring previously-missed renames are caught.
    Commits the transaction internally.
    """
    now = datetime.now(timezone.utc)

    user_result = await session.execute(
        select(UserAccount.discord_user_id).where(
            func.lower(UserAccount.rsn) == old_rsn.lower()
        )
    )
    discord_user_id = user_result.scalar_one_or_none()

    if discord_user_id:
        all_rsns_result = await session.execute(
            select(UserAccount.rsn).where(
                UserAccount.discord_user_id == discord_user_id,
                func.lower(UserAccount.rsn) != new_rsn.lower(),
            )
        )
        historical_rsns = [row[0] for row in all_rsns_result]
    else:
        historical_rsns = [old_rsn]

    for rsn in historical_rsns:
        await _cascade_rsn_single(session, rsn, new_rsn, now)

    await session.execute(
        update(UserAccount)
        .where(func.lower(UserAccount.rsn) == old_rsn.lower())
        .values(
            rsn=new_rsn,
            rsn_history=func.array_append(UserAccount.rsn_history, old_rsn),
        )
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
