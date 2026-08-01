from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import TileRaceEvent, TileRaceTeam, TileRepositoryTile
from app.routers.tilerace._discord_payload import COMMAND_CHANNEL
from app.routers.tilerace._requirement_text import requirement_lines
from app.routers.tilerace._roll_feed import announce

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def _item(item_id: int, name: str, quantity: int = 1) -> dict[str, Any]:
    return {"kind": "item", "item_id": item_id, "quantity": quantity, "name": name}


def _event(**overrides: Any) -> TileRaceEvent:
    base: dict[str, Any] = {
        "id": 12,
        "name": "Summer Tile Race",
        "cells": [{"path_position": 7, "tile_id": 204}],
    }
    return TileRaceEvent(**{**base, **overrides})


def _team(**overrides: Any) -> TileRaceTeam:
    base: dict[str, Any] = {
        "id": 31,
        "name": "Abyssal Ashes",
        "slug": "abyssal-ashes",
        "color": "#8b0000",
        "position": 7,
        "discord_text_channel_id": 900000000000000001,
    }
    return TileRaceTeam(**{**base, **overrides})


def _tile_row() -> TileRepositoryTile:
    return TileRepositoryTile(
        id=204,
        title="Bandos armour",
        description="Any two pieces from General Graardor.",
        icon_url="https://utfs.io/f/bandos.webp",
        items=[],
        requirement={
            "kind": "and",
            "children": [
                _item(11832, "Bandos chestplate"),
                _item(11834, "Bandos tassets", quantity=2),
            ],
        },
    )


def _session(tile: TileRepositoryTile | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = tile
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _published(valkey: AsyncMock) -> dict[str, Any]:
    channel, raw = valkey.publish.call_args.args
    assert channel == COMMAND_CHANNEL
    return json.loads(raw)


async def test_a_roll_publishes_the_tile_the_team_landed_on() -> None:
    valkey = AsyncMock()
    sent = await announce(
        _session(_tile_row()),
        valkey,
        _event(),
        _team(),
        {"dice": [2, 1], "total": 3, "skipped": False},
        111222333444555666,
        {},
    )

    assert sent is True
    command = _published(valkey)
    assert command["action"] == "roll"
    assert command["channel_id"] == "900000000000000001"
    assert command["rolled_by"] == "111222333444555666"
    assert command["roll"] == {
        "dice": [2, 1],
        "total": 3,
        "skipped": False,
        "new_position": 7,
    }
    assert command["tile"]["title"] == "Bandos armour"
    assert command["tile"]["requirements"] == [
        "- Bandos chestplate",
        "- Bandos tassets x2",
    ]


async def test_a_team_without_a_channel_publishes_nothing() -> None:
    valkey = AsyncMock()
    sent = await announce(
        _session(_tile_row()),
        valkey,
        _event(),
        _team(discord_text_channel_id=None),
        {"dice": [3], "total": 3, "skipped": False},
        1,
        {},
    )

    assert sent is False
    valkey.publish.assert_not_called()


async def test_an_empty_cell_carries_a_null_tile() -> None:
    valkey = AsyncMock()
    await announce(
        _session(None),
        valkey,
        _event(cells=[{"path_position": 7}]),
        _team(),
        {"dice": [1], "total": 1, "skipped": False},
        1,
        {},
    )

    assert _published(valkey)["tile"] is None


async def test_landing_effects_are_worded_for_the_team() -> None:
    valkey = AsyncMock()
    await announce(
        _session(_tile_row()),
        valkey,
        _event(),
        _team(),
        {"dice": [1], "total": 1, "skipped": False},
        1,
        {"moved_to": 3, "skip_next": True, "game_over": True},
    )

    assert _published(valkey)["notes"] == [
        "Moved to tile 3",
        "Trap: your next turn is skipped",
        "End pad reached - the race is over",
    ]


async def test_a_publish_failure_never_breaks_a_committed_roll() -> None:
    valkey = AsyncMock()
    valkey.publish.side_effect = RuntimeError("valkey is down")

    assert (
        await announce(
            _session(_tile_row()),
            valkey,
            _event(),
            _team(),
            {"dice": [1], "total": 1, "skipped": False},
            1,
            {},
        )
        is False
    )


def test_a_top_level_and_is_flattened() -> None:
    lines = requirement_lines(
        {"kind": "and", "children": [_item(1, "Rune bar"), _item(2, "Coal")]}
    )
    assert lines == ["- Rune bar", "- Coal"]


def test_an_or_names_the_choice_and_indents_its_branches() -> None:
    lines = requirement_lines(
        {"kind": "or", "children": [_item(1, "Dragon axe"), _item(2, "Infernal axe")]}
    )
    assert lines == ["- Any one of:", "  - Dragon axe", "  - Infernal axe"]


def test_a_not_reads_as_without() -> None:
    lines = requirement_lines({"kind": "not", "child": _item(1, "Bond")})
    assert lines == ["- Without:", "  - Bond"]


def test_a_single_child_group_drops_its_heading() -> None:
    assert requirement_lines({"kind": "or", "children": [_item(1, "Coal")]}) == [
        "- Coal"
    ]


def test_a_tile_with_no_requirement_has_no_lines() -> None:
    assert requirement_lines(None) == []


@pytest.mark.skipif(not _FIXTURES.exists(), reason="root fixtures/ not present")
async def test_the_published_command_matches_the_shared_fixture() -> None:
    fixture = json.loads((_FIXTURES / "tilerace_roll.json").read_text())
    valkey = AsyncMock()
    await announce(
        _session(_tile_row()),
        valkey,
        _event(),
        _team(),
        {"dice": [2, 1], "total": 3, "skipped": False},
        111222333444555666,
        {"skip_next": True},
    )

    assert _published(valkey) == fixture["command"]
