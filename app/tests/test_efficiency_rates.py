"""Unit tests for WOM efficiency-rate parsing and the reference rates endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from httpx import AsyncClient

from app.db.models import EfficiencyRate
from app.services.efficiency_rates._parse import parse_ehb, parse_ehp

_EHB = [
    {"boss": "zulrah", "rate": 45},
    {"boss": "vorkath", "rate": 32},
    {"boss": "bad", "rate": None},
]

_EHP = [
    {
        "skill": "ranged",
        "methods": [
            {"startExp": 0, "rate": 17000, "description": "Quests + void"},
            {"startExp": 449428, "rate": 842800, "description": "Black chins"},
        ],
        "bonuses": [],
    },
    {"skill": "defence", "methods": [], "bonuses": []},
]


def test_parse_ehb_skips_invalid() -> None:
    rows = parse_ehb(_EHB)
    assert {r.metric for r in rows} == {"zulrah", "vorkath"}
    zulrah = next(r for r in rows if r.metric == "zulrah")
    assert zulrah.kind == "ehb"
    assert zulrah.rate == 45.0


def test_parse_ehp_uses_peak_rate_and_keeps_tiers() -> None:
    rows = parse_ehp(_EHP)
    ranged = next(r for r in rows if r.metric == "ranged")
    assert ranged.kind == "ehp"
    assert ranged.rate == 842800.0
    assert len(ranged.payload["methods"]) == 2

    defence = next(r for r in rows if r.metric == "defence")
    assert defence.rate == 0.0


def _rate() -> EfficiencyRate:
    return EfficiencyRate(
        id=1,
        metric="zulrah",
        kind="ehb",
        rate=45.0,
        payload={},
        updated_at=datetime.now(UTC),
    )


async def test_list_rates(anon_client: AsyncClient, mock_session: MagicMock) -> None:
    mock_session.execute.return_value.scalars.return_value.all.return_value = [_rate()]
    resp = await anon_client.get("/reference/rates?kind=ehb")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["metric"] == "zulrah"
    assert body[0]["kind"] == "ehb"
    assert body[0]["rate"] == 45.0


async def test_list_rates_rejects_bad_kind(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/reference/rates?kind=nope")
    assert resp.status_code == 422
