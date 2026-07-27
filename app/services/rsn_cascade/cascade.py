from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    FrenzySubmission,
    Leaderboard,
    MemberGoals,
    PartyChatMessageDB,
    PartyDB,
    PartyMemberDB,
    PlayerRanking,
    PlayerSnapshot,
    User,
    UserAccount,
)


async def _cascade_rsn_single(
    session: AsyncSession, old_rsn: str, new_rsn: str, now: datetime
) -> None:
    """Update all data tables for one old_rsn -> new_rsn substitution. Does not commit."""
    await session.execute(
        update(User)
        .where(func.lower(User.rsn) == old_rsn.lower())
        .values(rsn=new_rsn, updated_at=now)
    )

    # Leaderboard has a composite PK; delete conflicting old rows before renaming.
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

    # PlayerRanking has unique constraint on rsn; copy to new_rsn if absent, then delete old.
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

    await session.execute(
        text(
            "INSERT INTO player_snapshots (rsn, skills, bosses, activities, fetched_at)"
            " SELECT :new_rsn, skills, bosses, activities, fetched_at"
            " FROM player_snapshots WHERE lower(rsn) = lower(:old_rsn)"
            " ON CONFLICT (rsn) DO NOTHING"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        delete(PlayerSnapshot).where(func.lower(PlayerSnapshot.rsn) == old_rsn.lower())
    )

    await session.execute(
        text(
            "INSERT INTO member_goals (discord_user_id, rsn, goals, share_token, updated_at)"
            " SELECT discord_user_id, :new_rsn, goals, share_token, updated_at"
            " FROM member_goals WHERE lower(rsn) = lower(:old_rsn)"
            " ON CONFLICT (discord_user_id, rsn) DO NOTHING"
        ),
        {"old_rsn": old_rsn, "new_rsn": new_rsn},
    )
    await session.execute(
        delete(MemberGoals).where(func.lower(MemberGoals.rsn) == old_rsn.lower())
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
    """Rename player_name across all tables when a user changes their RSN.

    Cascades all historical RSNs linked to the same user to ensure previously-missed
    renames are caught. Commits the transaction internally.
    """
    now = datetime.now(UTC)

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
            rsn=new_rsn, rsn_history=func.array_append(UserAccount.rsn_history, old_rsn)
        )
    )

    await session.commit()
