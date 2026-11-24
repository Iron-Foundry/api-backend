"""Repair stored broadcast events whose text carries the game's variable tags.

Each tagged events row gets the text, type, player and data ingest stores
today, plus the side effects ingest owed it: the loot total, the collection log
slots and count, and the personal-best leaderboard. A repaired row that
duplicates a stored row in the same minute is deleted instead. Rows that ingest
stores in another table (coffer, clan leave, expel) are listed and left as is.

Run with:
    DATABASE_URL=... uv run python scripts/repair_tagged_broadcasts.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import broadcast_repair_statements as sql
from app.services.broadcast_repair import planned_repair
from app.services.broadcast_repair_writes import stored_event, write_repair

_TAG = {"tag": sql.TAG_PATTERN}


async def _finish(engine: AsyncEngine, dry_run: bool) -> None:
    """Clear leaderboard rows under a tagged name, then link repaired players."""
    if dry_run:
        async with engine.connect() as conn:
            found = await conn.execute(sql.COUNT_TAGGED_LEADERBOARD, _TAG)
            count = found.scalar_one()
        print(f"Would delete {count} leaderboard row(s) under a tagged name.")
        return
    async with engine.begin() as conn:
        gone = await conn.execute(sql.DELETE_TAGGED_LEADERBOARD, _TAG)
        print(f"Deleted {gone.rowcount} leaderboard row(s) under a tagged name.")
        for statement in sql.LINK_EVENT_USERS:
            await conn.execute(statement)


async def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")
    engine = create_async_engine(url, echo=False)
    async with engine.connect() as conn:
        rows = (await conn.execute(sql.FETCH_TAGGED, _TAG)).mappings().all()
    print(f"Found {len(rows)} tagged event(s).")
    for row in rows:
        repair = planned_repair(stored_event(row))
        if repair is None:
            print(f"  [{row['id']}] left as is: {row['raw_message']!r}")
            continue
        outcome = "would update"
        if not dry_run:
            async with engine.begin() as conn:
                was_duplicate = await write_repair(
                    conn, repair, row["type"], row["timestamp"]
                )
            outcome = "deleted as duplicate" if was_duplicate else "updated"
        print(
            f"  [{row['id']}] {outcome}: {row['type']} -> {repair.type}"
            f" | player={repair.player_name} | data={repair.data}"
            f" | loot owed={repair.loot_value_owed}"
        )
    await _finish(engine, dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run("--dry-run" in sys.argv))
