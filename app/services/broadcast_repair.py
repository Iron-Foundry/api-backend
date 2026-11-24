"""Plan the repair of a stored broadcast event whose text carries variable tags.

It owns the pure half: from a stored events row it computes the text, and the
type, player and data that ingest stores today, plus the loot value the
player's total still owes. `scripts/reparse_events.py` uses `event_repair` for
rows without tags. It never touches the database. It plans no repair
for a kind that ingest stores outside the events table (coffer, clan leave,
expel).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.broadcast_event_shape import EventShape, StoredEvent, event_shape
from app.services.parser.broadcast_template import render_broadcast

_LOOT_TYPES = frozenset({"loot", "loot_key", "clue_item"})


@dataclass(frozen=True)
class EventRepair:
    id: int
    type: str
    player_name: str | None
    raw_message: str
    data: dict[str, Any]
    loot_value_owed: int


def _loot_value_owed(stored: StoredEvent, shape: EventShape) -> int:
    """Return the coin value the player's loot total lacks for this event."""
    value = shape.data.get("coin_value") if shape.type in _LOOT_TYPES else None
    if value is None:
        return 0
    same_credit = stored.type == shape.type and stored.player_name == shape.player_name
    counted = stored.data.get("coin_value") if same_credit else None
    return value - (counted or 0)


def event_repair(stored: StoredEvent, message: str) -> EventRepair | None:
    """Return the row ingest stores for the message, with the loot value owed.

    Returns None for a kind that ingest stores in another table.
    """
    shape = event_shape(message, stored)
    if shape is None:
        return None
    owed = _loot_value_owed(stored, shape)
    return EventRepair(
        stored.id, shape.type, shape.player_name, message, shape.data, owed
    )


def planned_repair(stored: StoredEvent) -> EventRepair | None:
    """Return the repair for a tagged row, or None when there is none to make."""
    message = render_broadcast(stored.raw_message)
    if message == stored.raw_message:
        return None
    return event_repair(stored, message)
