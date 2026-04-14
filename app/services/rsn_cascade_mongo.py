# DEPRECATED — MongoDB implementation. Kept for reference. Not imported in production.
from __future__ import annotations

from datetime import datetime, timezone

_PLAYER_NAME_COLLECTIONS = [
    "personal_bests",
    "collection_log_counts",
    "loot_totals",
]


async def cascade_rsn_change(db, old_rsn: str, new_rsn: str, clan_name: str) -> None:  # type: ignore[no-untyped-def]
    """Rename player_name across stat collections when a user changes their RSN.

    Scoped to clan_name to avoid cross-guild collisions.
    Called by the future name-change tracking service.
    Event collections are excluded for now.
    """
    for col in _PLAYER_NAME_COLLECTIONS:
        await db[col].update_many(
            {"player_name": old_rsn, "clan_name": clan_name},
            {"$set": {"player_name": new_rsn}},
        )
    for field in ("winner", "loser"):
        await db["pk_events"].update_many(
            {field: old_rsn, "clan_name": clan_name},
            {"$set": {field: new_rsn}},
        )
    await db["users"].update_one(
        {"rsn": old_rsn},
        {"$set": {"rsn": new_rsn, "updated_at": datetime.now(timezone.utc)}},
    )
