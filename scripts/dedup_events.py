"""One-time dedup: remove duplicate rows from the events table.

Duplicates are identified by (player_name, raw_message, date_trunc('minute', timestamp)).
For each duplicate group the row with the lowest id is kept; the rest are deleted.

Run with:
    DATABASE_URL=... uv run python scripts/dedup_events.py

Pass --dry-run to preview without deleting.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_FIND_SQL = text(
    """
    SELECT MIN(id) AS keep_id, array_agg(id ORDER BY id) AS all_ids
    FROM events
    WHERE player_name IS NOT NULL AND raw_message IS NOT NULL
    GROUP BY player_name, raw_message, date_trunc('minute', timestamp)
    HAVING COUNT(*) > 1
    """
)

_DELETE_SQL = text("DELETE FROM events WHERE id = ANY(:ids)")


async def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")

    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        result = await conn.execute(_FIND_SQL)
        groups = result.all()

    if not groups:
        print("No duplicate events found.")
        await engine.dispose()
        return

    total_dupes = 0
    ids_to_delete: list[int] = []
    for row in groups:
        dupes = [i for i in row.all_ids if i != row.keep_id]
        total_dupes += len(dupes)
        ids_to_delete.extend(dupes)

    print(f"Found {len(groups)} duplicate groups, {total_dupes} rows to delete.")

    if dry_run:
        print("Dry run — no rows deleted.")
        await engine.dispose()
        return

    async with engine.begin() as conn:
        result = await conn.execute(_DELETE_SQL, {"ids": ids_to_delete})
        print(f"Deleted {result.rowcount} duplicate event rows.")

    await engine.dispose()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run(dry_run))
