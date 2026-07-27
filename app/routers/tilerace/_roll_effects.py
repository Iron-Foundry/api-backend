from __future__ import annotations

import secrets
from typing import Any

from app.db.models import TileRaceTeam


def roll_dice_values(count: int, sides: int) -> list[int]:
    safe_count = max(1, count)
    safe_sides = max(1, sides)
    return [secrets.randbelow(safe_sides) + 1 for _ in range(safe_count)]


def find_cell(cells: list[dict[str, Any]], position: int) -> dict[str, Any] | None:
    for cell in cells:
        if cell.get("path_position") == position:
            return cell
    return None


def cell_is_gated(cell: dict[str, Any] | None) -> bool:
    return bool(cell and cell.get("tile_id"))


def apply_landing_modifiers(
    team: TileRaceTeam, cell: dict[str, Any] | None
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    effects = dict(team.pending_effects or {})
    for modifier in (cell or {}).get("modifiers", []):
        _apply_one(modifier, team, effects, summary)
    team.pending_effects = effects
    return summary


def cell_in_pad(cell: dict[str, Any] | None, pad: dict[str, Any] | None) -> bool:
    if not cell or not pad:
        return False
    x = cell.get("cell_x")
    y = cell.get("cell_y")
    if x is None or y is None:
        return False
    px = pad.get("cell_x", 0)
    py = pad.get("cell_y", 0)
    within_x = px <= x < px + pad.get("width", 1)
    within_y = py <= y < py + pad.get("height", 1)
    return within_x and within_y


def apply_pad_trigger(
    team: TileRaceTeam, pad: dict[str, Any] | None, summary: dict[str, Any]
) -> None:
    trigger = (pad or {}).get("trigger")
    if not trigger:
        return
    effects = dict(team.pending_effects or {})
    _apply_one(trigger, team, effects, summary)
    team.pending_effects = effects


def _apply_one(
    modifier: dict[str, Any],
    team: TileRaceTeam,
    effects: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    kind = modifier.get("type")
    if kind == "snakes_ladders":
        team.position = int(modifier.get("target_position", team.position))
        summary["moved_to"] = team.position
    elif kind == "bonus_penalty":
        effect = modifier.get("effect")
        if effect == "extra_roll":
            effects["extra_rolls"] = int(effects.get("extra_rolls", 0)) + 1
            summary["allow_extra_roll"] = True
        elif effect == "skip_turn":
            effects["skip_next"] = True
            summary["skip_next"] = True
        elif effect == "reroll":
            summary["reroll"] = True
