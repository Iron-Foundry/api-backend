from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.routers.frenzy._points import POINT_CAP, assign_item_points, round_half_up
from app.routers.frenzy._scoring import _calc_item_points

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def _points(tiers: dict[str, Any]) -> list[int]:
    return [
        item["points"]
        for tier in tiers.values()
        for source in tier["sources"]
        for item in source["items"]
    ]


@pytest.mark.skipif(not _FIXTURES.exists(), reason="root fixtures/ not present")
def test_points_match_shared_fixture() -> None:
    fixture = json.loads((_FIXTURES / "frenzy_points.json").read_text())
    assert fixture["point_cap"] == POINT_CAP
    for case in fixture["cases"]:
        assert _points(assign_item_points(case["tiers"])) == case["points"]


@pytest.mark.parametrize(("value", "expected"), [(0.5, 1), (2.5, 3), (2.49, 2)])
def test_round_half_up_rounds_halves_up(value: float, expected: int) -> None:
    assert round_half_up(value) == expected


def test_assign_drops_budget_and_lock_keys() -> None:
    tiers = {
        "Easy": {
            "budget_pct": 40,
            "sources": [
                {"name": "Obor", "items": [{"name": "Club", "points_locked": True}]}
            ],
        }
    }
    tier = assign_item_points(tiers)["Easy"]
    assert "budget_pct" not in tier
    assert "points_locked" not in tier["sources"][0]["items"][0]


@pytest.mark.parametrize(("obtained", "expected"), [(1, 5), (2, 8)])
def test_duplicate_half_rounds_up(obtained: int, expected: int) -> None:
    item = {"points": 5, "required": 1, "duplicate_required": 1}
    assert _calc_item_points(item, obtained) == expected
