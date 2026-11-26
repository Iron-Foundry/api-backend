"""Write the WOM in-game clan ranks to users, user accounts and wom_clan_ranks."""

from __future__ import annotations

from typing import Any, cast

from loguru import logger
from sqlalchemy import ARRAY, Text, bindparam, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def sync_wom_ranks(
    session_factory: async_sessionmaker[AsyncSession], memberships: list[dict[str, Any]]
) -> None:
    """Bulk-write WOM in-game ranks to users.clan_rank for all matched members."""
    wom_ranks: dict[str, str] = {
        m["player"]["username"].lower(): m["role"]
        for m in memberships
        if m.get("player") and m.get("role")
    }
    if not wom_ranks:
        return

    rsns = list(wom_ranks.keys())
    roles = list(wom_ranks.values())

    _arr = ARRAY(Text())
    _params = [bindparam("rsns", type_=_arr), bindparam("roles", type_=_arr)]

    async with session_factory() as session:
        r1 = cast(
            CursorResult[Any],
            await session.execute(
                text("""
                UPDATE users u
                   SET clan_rank  = wd.role,
                       updated_at = now()
                  FROM (SELECT unnest(:rsns) AS rsn,
                               unnest(:roles) AS role) AS wd
                  JOIN user_accounts ua ON lower(ua.rsn) = wd.rsn
                 WHERE ua.discord_user_id = u.discord_user_id
                   AND (u.clan_rank IS DISTINCT FROM wd.role)
            """).bindparams(*_params),
                {"rsns": rsns, "roles": roles},
            ),
        )
        r2 = cast(
            CursorResult[Any],
            await session.execute(
                text("""
                UPDATE users u
                   SET clan_rank  = wd.role,
                       updated_at = now()
                  FROM (SELECT unnest(:rsns) AS rsn,
                               unnest(:roles) AS role) AS wd
                 WHERE lower(u.rsn) = wd.rsn
                   AND (u.clan_rank IS DISTINCT FROM wd.role)
            """).bindparams(*_params),
                {"rsns": rsns, "roles": roles},
            ),
        )
        await session.execute(
            text("""
                INSERT INTO wom_clan_ranks (rsn, clan_rank, updated_at)
                SELECT wd.rsn, wd.role, now()
                  FROM (SELECT unnest(:rsns) AS rsn,
                               unnest(:roles) AS role) AS wd
                ON CONFLICT (rsn) DO UPDATE
                       SET clan_rank  = EXCLUDED.clan_rank,
                           updated_at = EXCLUDED.updated_at
                     WHERE wom_clan_ranks.clan_rank IS DISTINCT FROM EXCLUDED.clan_rank
            """).bindparams(*_params),
            {"rsns": rsns, "roles": roles},
        )
        await session.commit()

    logger.info(
        "WOM rank sync: updated {} (user_accounts) + {} (legacy rsn)",
        r1.rowcount,
        r2.rowcount,
    )
