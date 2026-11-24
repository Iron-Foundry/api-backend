from __future__ import annotations

from typing import Any

import pytest

from app.services.broadcast_event_shape import StoredEvent
from app.services.broadcast_repair import EventRepair, planned_repair

_LOOT = (
    "Kz Grind received a drop: <int_0=2><int_0:spacer> x Spirit seed"
    "<int_0=280000> (<int_0:spacer> coins)."
)
_XP = "<int_0=162000000>Ursaring has reached <int_0:spacer> XP in Ranged."
_PET = (
    "<int_p1=0>GIMTUNABARGE has a funny feeling like "
    "<switch,int_p1,he's,she's,they're> being followed: "
    "<int_0=32>Tumeken's guardian at <int_0:spacer> completions."
)
_QUEST = (
    "<str_quest_name_0=Legends' Quest>V0xes has completed a quest: <str_quest_name_0>"
)
_ESCAPED_LOOT = "X received a drop: Bones <lt>3 (100 coins)."


def _stored(
    type_: str, player: str | None, raw: str, data: dict[str, Any]
) -> StoredEvent:
    return StoredEvent(
        id=7,
        type=type_,
        player_name=player,
        sender="Iron Foundry",
        raw_message=raw,
        data=data,
    )


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (
            _stored(
                "loot",
                "Kz Grind",
                _LOOT,
                {"item_name": "tagged", "coin_value": None, "rank": "iron"},
            ),
            EventRepair(
                7,
                "loot",
                "Kz Grind",
                "Kz Grind received a drop: 2 x Spirit seed (280,000 coins).",
                {
                    "item_name": "Spirit seed",
                    "coin_value": 280000,
                    "source": "Generic PVM",
                    "rank": "iron",
                    "sender": "Iron Foundry",
                },
                280000,
            ),
        ),
        (
            _stored("unknown", None, _XP, {}),
            EventRepair(
                7,
                "xp_milestone",
                "Ursaring",
                "Ursaring has reached 162,000,000 XP in Ranged.",
                {"skill": "Ranged", "xp": 162000000},
                0,
            ),
        ),
        (
            _stored("unknown", None, _PET, {}),
            EventRepair(
                7,
                "pet",
                "GIMTUNABARGE",
                "GIMTUNABARGE has a funny feeling like he's being followed: "
                "Tumeken's guardian at 32 completions.",
                {},
                0,
            ),
        ),
        (
            _stored("quest", "<str_quest_name_0=Legends' Quest>V0xes", _QUEST, {}),
            EventRepair(
                7,
                "quest",
                "V0xes",
                "V0xes has completed a quest: Legends' Quest",
                {"achievement_type": "quest", "name": "Legends' Quest"},
                0,
            ),
        ),
        (
            _stored("loot", "X", _ESCAPED_LOOT, {"coin_value": 100}),
            EventRepair(
                7,
                "loot",
                "X",
                "X received a drop: Bones <3 (100 coins).",
                {
                    "item_name": "Bones <3",
                    "coin_value": 100,
                    "source": "Generic PVM",
                    "rank": None,
                    "sender": "Iron Foundry",
                },
                0,
            ),
        ),
        (_stored("loot", "X", "X received a drop: Bones.", {}), None),
    ],
)
def test_planned_repair_matches_ingest_shape(
    stored: StoredEvent, expected: EventRepair | None
) -> None:
    assert planned_repair(stored) == expected
