"""Write a planned event repair, with the side effects that ingest owed the row.

`scripts/repair_tagged_broadcasts.py` and `scripts/reparse_events.py` use it.
The side effects are the loot total, the collection log slots and count, and
the personal-best leaderboard. A repaired row that duplicates a stored row in
the same minute is deleted instead, because the stored row already has them.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import broadcast_repair_statements as sql
from app.services.broadcast_event_shape import StoredEvent
from app.services.broadcast_repair import EventRepair


def stored_event(row: RowMapping) -> StoredEvent:
    """Return the stored event of a fetched events row."""
    return StoredEvent(
        id=row["id"],
        type=row["type"],
        player_name=row["player_name"],
        sender=row["sender"],
        raw_message=row["raw_message"],
        data=row["data"] or {},
    )


async def _apply_side_effects(
    conn: AsyncConnection, repair: EventRepair, was_type: str
) -> None:
    data, player = repair.data, repair.player_name
    if repair.loot_value_owed:
        owed = {"value": repair.loot_value_owed, "player": player}
        await conn.execute(sql.ADD_LOOT_VALUE, owed)
    if repair.type == "collection_log":
        slots = {"slots": data["log_slots"], "max": data["log_slots_max"]}
        await conn.execute(sql.RAISE_CLOG_SLOTS, {**slots, "player": player})
        if was_type != "collection_log":
            await conn.execute(sql.COUNT_CLOG)
    if repair.type == "personal_best":
        pb = {"activity": data["activity"], "variant": data["variant"]}
        pb |= {"time": data["time_seconds"], "player": player}
        await conn.execute(sql.UPSERT_PERSONAL_BEST, pb)


async def write_repair(
    conn: AsyncConnection, repair: EventRepair, was_type: str, timestamp: datetime
) -> bool:
    """Write one repair and return True when the row was a duplicate."""
    key = {"id": repair.id, "player": repair.player_name, "raw": repair.raw_message}
    if repair.player_name is not None:
        found = await conn.execute(sql.FIND_DUPLICATE, {**key, "ts": timestamp})
        if found.first() is not None:
            await conn.execute(sql.DELETE_EVENT, {"id": repair.id})
            return True
    values = {**key, "type": repair.type, "data": json.dumps(repair.data)}
    await conn.execute(sql.UPDATE_EVENT, values)
    await _apply_side_effects(conn, repair, was_type)
    return False
