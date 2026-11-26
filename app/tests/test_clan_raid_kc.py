from __future__ import annotations

from typing import Any

from app.services.clan_stats import raid_kc_totals


def _entry(bosses: dict[str, int]) -> dict[str, Any]:
    return {"data": {"data": {"bosses": {k: {"kills": v} for k, v in bosses.items()}}}}


def test_raid_totals_sum_modes_and_skip_unranked() -> None:
    entries = [
        _entry({"chambers_of_xeric": 10, "chambers_of_xeric_challenge_mode": 2}),
        _entry({"the_fractured_archive": 7, "theatre_of_blood": -1}),
        {"data": None},
    ]
    assert raid_kc_totals(entries) == {
        "cox_kc": 12,
        "tob_kc": 0,
        "toa_kc": 0,
        "tfa_kc": 7,
    }
