from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers.frenzy._snake import (
    FULL,
    TOP_PICKS,
    hand_out,
    manual_picks_left,
    snake_slot,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.mark.skipif(not _FIXTURES.exists(), reason="root fixtures/ not present")
def test_snake_matches_shared_fixture() -> None:
    cases = json.loads((_FIXTURES / "frenzy_snake.json").read_text())["cases"]
    for case in cases:
        count = case["team_count"]
        slots = [snake_slot(p, count) for p in range(1, len(case["slots"]) + 1)]
        assert slots == case["slots"]


def test_hand_out_continues_mid_round() -> None:
    assert hand_out([10, 20], 3, [7, 8, 9]) == [(7, 20, 3), (8, 10, 4), (9, 10, 5)]


@pytest.mark.parametrize(
    ("mode", "next_pick", "pool", "manual"),
    [
        (TOP_PICKS, 4, 10, True),
        (TOP_PICKS, 5, 10, False),
        (FULL, 5, 10, True),
        (FULL, 5, 0, False),
    ],
)
def test_manual_picks_stop_after_top_rounds(
    mode: str, next_pick: int, pool: int, manual: bool
) -> None:
    assert manual_picks_left(mode, 2, next_pick, 2, pool) is manual
