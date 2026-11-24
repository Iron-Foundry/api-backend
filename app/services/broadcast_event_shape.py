"""Compute the type, player and data that ingest stores for a broadcast message.

It owns the pure map from a clean message to the events row that the ingest
handlers write. It reads the stored row only for the loot rank and sender,
because the message does not carry them. It never touches the database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services import parser
from app.services.parser import (
    BroadcastType,
    ParsedAchievement,
    ParsedPersonalBest,
    ParsedPk,
)

_PARSERS: dict[BroadcastType, Callable[[str], Any]] = {
    BroadcastType.LOOT: parser.parse_loot,
    BroadcastType.LEVEL_UP: parser.parse_level_up,
    BroadcastType.XP_MILESTONE: parser.parse_xp_milestone,
    BroadcastType.QUEST: parser.parse_achievement,
    BroadcastType.DIARY: parser.parse_achievement,
    BroadcastType.COMBAT_ACHIEVEMENT: parser.parse_achievement,
    BroadcastType.PET: parser.parse_pet,
    BroadcastType.NEW_MEMBER: parser.parse_new_member,
    BroadcastType.COLLECTION_LOG: parser.parse_collection_log,
    BroadcastType.LOOT_KEY: parser.parse_loot_key,
    BroadcastType.CLUE_ITEM: parser.parse_clue_item,
    BroadcastType.PK: parser.parse_pk,
    BroadcastType.PERSONAL_BEST: parser.parse_personal_best,
    BroadcastType.HCIM_DEATH: parser.parse_hcim_death,
    BroadcastType.LEAGUE_RELIC: parser.parse_league_relic,
    BroadcastType.LEAGUE_RANK: parser.parse_league_rank,
    BroadcastType.LEAGUE_AREA: parser.parse_league_area,
}
_STORED_ELSEWHERE = frozenset(
    {
        BroadcastType.COFFER_DONATION,
        BroadcastType.COFFER_WITHDRAWAL,
        BroadcastType.LEFT_CLAN,
        BroadcastType.EXPELLED,
    }
)
_EVENT_TYPE = {BroadcastType.LEVEL_UP: "level"}


@dataclass(frozen=True)
class StoredEvent:
    id: int
    type: str
    player_name: str | None
    sender: str | None
    raw_message: str
    data: dict[str, Any]


@dataclass(frozen=True)
class EventShape:
    type: str
    player_name: str | None
    data: dict[str, Any]


def _event_data(parsed: Any, stored: StoredEvent, event_type: str) -> dict[str, Any]:
    """Return the data dict the ingest handler for this kind stores."""
    if isinstance(parsed, ParsedAchievement):
        data: dict[str, Any] = {"achievement_type": parsed.kind, "name": parsed.name}
        if parsed.difficulty:
            data["difficulty"] = parsed.difficulty
        return data
    data = {k: v for k, v in dataclasses.asdict(parsed).items() if k != "player_name"}
    if isinstance(parsed, ParsedPersonalBest):
        data["variant"] = parsed.variant or ""
    if event_type == "loot":
        data["rank"] = stored.data.get("rank")
        data["sender"] = stored.data.get("sender", stored.sender)
    return data


def event_shape(message: str, stored: StoredEvent) -> EventShape | None:
    """Return the row ingest stores for the message.

    Returns None for a kind that ingest stores in another table.
    """
    kind = parser.classify(message)
    if kind in _STORED_ELSEWHERE:
        return None
    parse = _PARSERS.get(kind)
    parsed = parse(message) if parse else None
    if parsed is None:
        return EventShape("unknown", None, {})
    event_type = _EVENT_TYPE.get(kind, kind.value)
    if isinstance(parsed, ParsedAchievement):
        event_type = parsed.kind
    player = parsed.winner if isinstance(parsed, ParsedPk) else parsed.player_name
    return EventShape(event_type, player, _event_data(parsed, stored, event_type))
