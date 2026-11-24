"""Reparse stored events whose type or data differs from what ingest stores today.

Targets the rows of type unknown, combat_achievement and personal_best. Each
row gets the type, player and data that ingest writes for its text, plus the
side effects ingest owed it: the loot total, the collection log slots and
count, and the personal-best leaderboard. A row that then duplicates a stored
row in the same minute is deleted instead. The script never changes
'timestamp', 'id', 'sender', 'raw_message' or 'is_league_world'.

Run with:
    DATABASE_URL=... uv run python scripts/reparse_events.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import broadcast_repair_statements as sql
from app.services.broadcast_repair import EventRepair, event_repair
from app.services.broadcast_repair_writes import stored_event, write_repair

_FETCH_SQL = text(
    "SELECT id, type, player_name, sender, raw_message, data, timestamp"
    " FROM events WHERE raw_message IS NOT NULL"
    " AND type IN ('unknown', 'combat_achievement', 'personal_best') ORDER BY id"
)


def _changed_repair(row: RowMapping) -> EventRepair | None:
    """Return the repair of a row, or None when the row already has its shape."""
    stored = stored_event(row)
    repair = event_repair(stored, stored.raw_message)
    if repair is None or repair.type == "unknown":
        return None
    current = (stored.type, stored.player_name, stored.data)
    return None if (repair.type, repair.player_name, repair.data) == current else repair


async def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")
    engine = create_async_engine(url, echo=False)
    async with engine.connect() as conn:
        rows = (await conn.execute(_FETCH_SQL)).mappings().all()
    print(f"Inspecting {len(rows)} events...")
    changes = [(row, repair) for row in rows if (repair := _changed_repair(row))]
    for row, repair in changes:
        print(
            f"  [{row['id']}] {row['type']} -> {repair.type}"
            f" | player={repair.player_name} | data={repair.data}"
            f" | loot owed={repair.loot_value_owed}"
        )
    print(f"{'Would update' if dry_run else 'Updating'} {len(changes)} event(s).")
    if not dry_run and changes:
        deleted = 0
        for row, repair in changes:
            async with engine.begin() as conn:
                deleted += await write_repair(
                    conn, repair, row["type"], row["timestamp"]
                )
        print(f"Updated {len(changes) - deleted}, deleted {deleted} duplicate(s).")
        async with engine.begin() as conn:
            for statement in sql.LINK_EVENT_USERS:
                await conn.execute(statement)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run("--dry-run" in sys.argv))
