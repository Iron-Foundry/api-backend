"""Populate user_accounts from users.rsn for accounts predating the user_accounts table.

For every user who has users.rsn set but no user_accounts entry, inserts a
primary user_accounts row. Safe to run multiple times (skips existing entries).

Run with:
    DATABASE_URL=... uv run python scripts/populate_user_accounts.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_FIND_SQL = text(
    """
    SELECT u.discord_user_id, u.rsn
    FROM users u
    WHERE u.rsn IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM user_accounts ua
          WHERE ua.discord_user_id = u.discord_user_id
      )
    ORDER BY u.discord_user_id
    """
)

_INSERT_SQL = text(
    """
    INSERT INTO user_accounts (discord_user_id, rsn, is_primary, created_at)
    VALUES (:discord_user_id, :rsn, true, :created_at)
    ON CONFLICT DO NOTHING
    """
)

_NORMALIZE_NBSP_SQL = text(
    """
    UPDATE events
    SET player_name = replace(player_name, chr(160), ' ')
    WHERE player_name LIKE '%' || chr(160) || '%'
    """
)

_LINK_EVENTS_SQL = text(
    """
    UPDATE events e
    SET user_id = u.discord_user_id
    FROM (
        SELECT discord_user_id, lower(rsn) AS rsn_lower FROM user_accounts
        UNION
        SELECT discord_user_id, lower(rsn) FROM users WHERE rsn IS NOT NULL
    ) u
    WHERE lower(e.player_name) = u.rsn_lower
      AND e.user_id IS NULL
    """
)


async def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")

    engine = create_async_engine(url, echo=False)

    async with engine.connect() as conn:
        result = await conn.execute(_FIND_SQL)
        rows = result.mappings().all()

    if not rows:
        print("No users missing user_accounts entries.")
        await engine.dispose()
        return

    print(f"Found {len(rows)} user(s) with users.rsn but no user_accounts entry:")
    for row in rows:
        print(f"  discord_user_id={row['discord_user_id']}  rsn={row['rsn']!r}")

    if dry_run:
        print("Dry-run: no changes made.")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    inserted = 0
    for row in rows:
        async with engine.begin() as conn:
            await conn.execute(
                _INSERT_SQL,
                {
                    "discord_user_id": row["discord_user_id"],
                    "rsn": row["rsn"],
                    "created_at": now,
                },
            )
        inserted += 1

    print(f"Inserted {inserted} user_accounts row(s).")

    async with engine.begin() as conn:
        result = await conn.execute(_NORMALIZE_NBSP_SQL)
        print(f"Normalized non-breaking spaces in {result.rowcount} event player_name(s).")

    async with engine.begin() as conn:
        result = await conn.execute(_LINK_EVENTS_SQL)
        print(f"Linked user_id for {result.rowcount} event(s).")

    await engine.dispose()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run(dry_run))
