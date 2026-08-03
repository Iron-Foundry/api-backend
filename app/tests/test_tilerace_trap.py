from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter, ValidationError

from app.db.models import TileRaceEvent, TileRaceTeam
from app.routers.tilerace._roll_effects import apply_landing_modifiers, cell_is_gated
from app.routers.tilerace._roll_feed import announce
from app.routers.tilerace.modifier_schema import Modifier

_ADAPTER = TypeAdapter(Modifier)


def _trap(dice_count: int = 3, dice_sides: int = 1) -> dict[str, Any]:
    return {"type": "trap", "dice_count": dice_count, "dice_sides": dice_sides}


def _cell(position: int, *modifiers: dict[str, Any]) -> dict[str, Any]:
    return {"path_position": position, "modifiers": list(modifiers)}


def _team(position: int, **overrides: Any) -> TileRaceTeam:
    base: dict[str, Any] = {
        "id": 31,
        "name": "Abyssal Ashes",
        "slug": "abyssal-ashes",
        "color": "#8b0000",
        "position": position,
        "pending_effects": {},
    }
    return TileRaceTeam(**{**base, **overrides})


def test_a_trap_sends_the_team_back_by_its_own_roll() -> None:
    team = _team(12)
    summary = apply_landing_modifiers(team, _cell(12, _trap()))

    assert team.position == 9
    assert summary["trap"] == {"dice": [1, 1, 1], "total": 3, "from": 12, "to": 9}


def test_a_trap_is_recorded_so_the_same_tile_never_bites_twice() -> None:
    team = _team(12)
    apply_landing_modifiers(team, _cell(12, _trap()))
    assert team.pending_effects["traps_sprung"] == [12]

    team.position = 12
    summary = apply_landing_modifiers(team, _cell(12, _trap()))

    assert team.position == 12
    assert "trap" not in summary
    assert summary["trap_spent"] == 12


def test_another_trap_on_the_board_still_bites() -> None:
    team = _team(12)
    apply_landing_modifiers(team, _cell(12, _trap()))

    team.position = 20
    summary = apply_landing_modifiers(team, _cell(20, _trap(dice_count=2)))

    assert team.position == 18
    assert summary["trap"]["from"] == 20
    assert team.pending_effects["traps_sprung"] == [12, 20]


def test_a_trap_never_pushes_a_team_behind_the_start() -> None:
    team = _team(2)
    apply_landing_modifiers(team, _cell(2, _trap(dice_count=5, dice_sides=1)))

    assert team.position == 0


def test_the_setback_stays_inside_the_traps_own_dice() -> None:
    for _ in range(40):
        team = _team(60)
        summary = apply_landing_modifiers(team, _cell(60, _trap(2, 6)))
        assert 2 <= summary["trap"]["total"] <= 12
        assert team.position == 60 - summary["trap"]["total"]


def test_a_trap_reads_its_setback_from_the_cell_not_a_moved_marker() -> None:
    """A jump earlier in the same cell must not shift where the trap counts from."""
    team = _team(12)
    apply_landing_modifiers(
        team, _cell(12, {"type": "snakes_ladders", "target_position": 30}, _trap())
    )

    assert team.position == 9
    assert team.pending_effects["traps_sprung"] == [12]


def test_a_trap_cell_never_gates_the_next_roll() -> None:
    """A trap carries no requirements, so standing on one needs no staff review.

    That holds on the landing that springs it and on every landing after, when
    the trap is spent and the team is simply parked on it.
    """
    trap_cell = _cell(12, _trap())
    assert cell_is_gated(trap_cell) is False

    team = _team(12)
    apply_landing_modifiers(team, trap_cell)
    team.position = 12
    apply_landing_modifiers(team, trap_cell)

    assert cell_is_gated(trap_cell) is False


def test_the_schema_accepts_a_trap_and_bounds_its_dice() -> None:
    parsed = _ADAPTER.validate_python(_trap(2, 8))
    assert (parsed.dice_count, parsed.dice_sides) == (2, 8)

    assert _ADAPTER.validate_python({"type": "trap"}).dice_sides == 6

    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(_trap(dice_count=9))
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(_trap(dice_sides=99))


async def test_the_team_channel_is_told_what_the_trap_did() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    valkey = AsyncMock()

    await announce(
        session,
        valkey,
        TileRaceEvent(id=12, name="Summer Tile Race", cells=[{"path_position": 9}]),
        _team(9, discord_text_channel_id=900000000000000001),
        {"dice": [4], "total": 4, "skipped": False},
        1,
        {"trap": {"dice": [1, 1, 1], "total": 3, "from": 12, "to": 9}},
    )

    _, raw = valkey.publish.call_args.args
    assert json.loads(raw)["notes"] == [
        "Trap on tile 12! Rolled 3 and slid back to tile 9"
    ]


async def test_the_team_is_told_the_tile_they_slid_back_to_is_open_again() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    valkey = AsyncMock()

    await announce(
        session,
        valkey,
        TileRaceEvent(id=12, name="Summer Tile Race", cells=[{"path_position": 9}]),
        _team(9, discord_text_channel_id=900000000000000001),
        {"dice": [4], "total": 4, "skipped": False},
        1,
        {
            "trap": {"dice": [1, 1, 1], "total": 3, "from": 12, "to": 9},
            "tiles_reset": [9, 10, 11],
        },
    )

    _, raw = valkey.publish.call_args.args
    assert json.loads(raw)["notes"] == [
        "Trap on tile 12! Rolled 3 and slid back to tile 9",
        "Tiles 9, 10, 11 must be completed again",
    ]


async def test_a_single_reopened_tile_is_worded_in_the_singular() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    valkey = AsyncMock()

    await announce(
        session,
        valkey,
        TileRaceEvent(id=12, name="Summer Tile Race", cells=[{"path_position": 9}]),
        _team(9, discord_text_channel_id=900000000000000001),
        {"dice": [4], "total": 4, "skipped": False},
        1,
        {"tiles_reset": [9]},
    )

    _, raw = valkey.publish.call_args.args
    assert json.loads(raw)["notes"] == ["Tile 9 must be completed again"]


async def test_a_spent_trap_is_called_out_rather_than_passed_over() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    valkey = AsyncMock()

    await announce(
        session,
        valkey,
        TileRaceEvent(id=12, name="Summer Tile Race", cells=[{"path_position": 12}]),
        _team(12, discord_text_channel_id=900000000000000001),
        {"dice": [4], "total": 4, "skipped": False},
        1,
        {"trap_spent": 12},
    )

    _, raw = valkey.publish.call_args.args
    assert json.loads(raw)["notes"] == ["Trap on tile 12 is already sprung"]
