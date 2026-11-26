"""Foundry's staff-set kill rate fills a drop source only where OSRSClans has none."""

from __future__ import annotations

import pytest

from app.services.osrsclans.foundry_rates import with_foundry_rate
from app.services.osrsclans.loot_rate_models import LootSource


def _source(kills_per_hour: float | None, measurer: str | None) -> LootSource:
    return LootSource.model_validate(
        {
            "source": "Herbiboar",
            "page": "Herbiboar",
            "section": None,
            "category": "skilling",
            "dropTypes": ["hunter"],
            "rows": 12,
            "killsPerHour": kills_per_hour,
            "killsPerHourIronman": None,
            "killRateSource": measurer,
            "womMetric": None,
        }
    )


@pytest.mark.parametrize(
    ("kills_per_hour", "measurer", "rates", "expected"),
    [
        (None, None, {"Herbiboar": 80.0}, (80.0, "foundry")),
        (None, None, {"Other": 80.0}, (None, None)),
        (55.0, "droptracker", {"Herbiboar": 80.0}, (55.0, "droptracker")),
    ],
)
def test_foundry_rate_fills_only_rateless_sources(
    kills_per_hour: float | None,
    measurer: str | None,
    rates: dict[str, float],
    expected: tuple[float | None, str | None],
) -> None:
    filled = with_foundry_rate(_source(kills_per_hour, measurer), rates)
    assert (filled.kills_per_hour, filled.kill_rate_source) == expected
