"""A saved frenzy template stores the points the server sets from the fixed cap."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _tiers(points: int) -> dict[str, object]:
    item = {"name": "Scurry", "drop_denom": 3000, "kph": 60, "points": points}
    return {
        "Easy": {
            "budget_pct": 100,
            "sources": [{"name": "Scurrius", "items": [item]}],
        }
    }


async def test_saved_template_gets_capped_points(staff_client: AsyncClient) -> None:
    created = await staff_client.post(
        "/frenzy/templates", json={"name": "Cap", "tiers": _tiers(7)}
    )
    path = f"/frenzy/templates/{created.json()['id']}"
    await staff_client.put(path, json={"name": "Cap", "tiers": _tiers(9)})

    tier = (await staff_client.get(path)).json()["tiers"]["Easy"]
    assert tier["sources"][0]["items"][0]["points"] == 666667
    assert "budget_pct" not in tier
