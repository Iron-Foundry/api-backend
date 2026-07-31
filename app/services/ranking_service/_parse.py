from __future__ import annotations

from datetime import datetime
from typing import Any

_OVERALL = "overall"


def _metric_value(info: Any, key: str) -> float:
    if isinstance(info, dict):
        return float(info.get(key, 0) or 0)
    return float(info or 0)


def _efficiency(player: dict[str, Any], key: str) -> float | None:
    value = player.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def build_snapshot_rows(
    bulk: list[dict[str, Any]], skill_names: set[str], fetched_at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a WOM bulk-hiscores response into ranking inputs and snapshot rows.

    Ranking inputs carry only the configured skills; snapshot rows also carry
    overall XP and the player's WOM-computed EHP/EHB.
    """
    ranking_inputs: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []

    for entry in bulk:
        player = entry.get("player") or {}
        rsn = player.get("username", "").lower()
        if not rsn:
            continue
        snapshot_data = entry.get("data")
        if not snapshot_data:
            continue
        data = snapshot_data.get("data", {})
        raw_skills: dict[str, Any] = data.get("skills", {})
        skills = {
            n: _metric_value(info, "experience")
            for n, info in raw_skills.items()
            if n in skill_names
        }
        bosses = {
            n: int(_metric_value(info, "kills"))
            for n, info in data.get("bosses", {}).items()
        }
        activities = {
            n: int(_metric_value(info, "score"))
            for n, info in data.get("activities", {}).items()
        }
        ranking_inputs.append({"rsn": rsn, "skills": skills, "bosses": bosses})
        snapshot_rows.append(
            {
                "rsn": rsn,
                "skills": {
                    **skills,
                    _OVERALL: _metric_value(raw_skills.get(_OVERALL), "experience"),
                },
                "bosses": bosses,
                "activities": activities,
                "ehp": _efficiency(player, "ehp"),
                "ehb": _efficiency(player, "ehb"),
                "fetched_at": fetched_at,
            }
        )

    return ranking_inputs, snapshot_rows
