from __future__ import annotations

import pytest

from app.services.broadcast_event_shape import EventShape, StoredEvent, event_shape


def _stored(raw: str) -> StoredEvent:
    return StoredEvent(
        id=1,
        type="unknown",
        player_name=None,
        sender="Iron Foundry",
        raw_message=raw,
        data={},
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "X has reached level 99 in Ranged.",
            EventShape("level", "X", {"skill": "Ranged", "new_level": 99}),
        ),
        (
            "X achieved a new Corp Beast personal best: 1:23.40",
            EventShape(
                "personal_best",
                "X",
                {"activity": "Corp Beast", "time_seconds": 83.4, "variant": ""},
            ),
        ),
        (
            "X received a drop: Bones (100 coins).",
            EventShape(
                "loot",
                "X",
                {
                    "item_name": "Bones",
                    "coin_value": 100,
                    "source": "Generic PVM",
                    "rank": None,
                    "sender": "Iron Foundry",
                },
            ),
        ),
        ("X has deposited 5,000 coins into the coffer.", None),
        ("X says hello", EventShape("unknown", None, {})),
    ],
)
def test_event_shape_matches_ingest_row(
    message: str, expected: EventShape | None
) -> None:
    assert event_shape(message, _stored(message)) == expected
