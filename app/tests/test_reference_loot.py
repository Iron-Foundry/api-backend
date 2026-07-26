"""Unit tests for the wiki drop parser and the reference loot endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.db.models import LootDrop, LootSource
from app.services.loot_tables._catalog import load_catalog
from app.services.loot_tables._drops import (
    parse_drop_tables,
    parse_quantity,
    parse_rarity,
)


def test_catalog_chest_remaps_and_excludes() -> None:
    entries = {e.slug: e for e in load_catalog()}

    assert entries["chambers_of_xeric"].wiki_page == "Ancient chest"
    assert entries["barrows_chests"].wiki_page == "Chest (Barrows)"
    assert entries["sol_heredit"].wiki_page == "Rewards Chest (Fortis Colosseum)"
    assert entries["wintertodt"].wiki_page == "Supply crate (Wintertodt)"

    assert entries["chambers_of_xeric"].reward_kind == "chest"
    assert entries["wintertodt"].reward_kind == "chest"
    assert entries["zulrah"].reward_kind is None

    assert "chambers_of_xeric_challenge_mode" not in entries
    assert "theatre_of_blood_hard_mode" not in entries
    assert "tombs_of_amascut_expert" not in entries


_WIKITEXT = """
==Fight overview==
Some combat text with a {{DropsLine|name=Ignored|quantity=1|rarity=1/1}} outside drops.

==Drops==
===100%===
{{DropsTableHead}}
{{DropsLine|name=Zulrah's scales|quantity=100-299|rarity=Always}}
{{DropsTableBottom}}

===Uniques===
{{DropsTableHead}}
{{DropsLine|name=Tanzanite fang|quantity=1|rarity=1/1024|rolls=2}}
{{DropsLine|name=Flax|quantity=1000 (noted)|rarity=10/249|rolls=2}}
{{DropsTableBottom}}

==Loot table==
===Runes===
{{DropsTableHead}}
{{DropsLineReward|name=Blood rune|quantity=84-876|rarity=Common}}
{{DropsTableBottom}}

==Changes==
{{DropsLine|name=AlsoIgnored|quantity=1|rarity=1/1}}
"""


def test_parse_quantity_variants() -> None:
    assert parse_quantity("1") == (1, 1, False)
    assert parse_quantity("100-299") == (100, 299, False)
    assert parse_quantity("1000 (noted)") == (1000, 1000, True)
    assert parse_quantity("1,000") == (1000, 1000, False)
    assert parse_quantity("Unknown") == (0, 0, False)


def test_parse_rarity_variants() -> None:
    assert parse_rarity("Always") == (1, 1, None)
    assert parse_rarity("1/1024") == (1, 1024, None)
    assert parse_rarity("1/13,107") == (1, 13107, None)
    assert parse_rarity("{{Frac|3|10}}") == (3, 10, None)
    assert parse_rarity("Uncommon") == (None, None, "Uncommon")


def test_parse_rarity_varies_is_blanked() -> None:
    assert parse_rarity("Varies") == (None, None, None)


def test_parse_rarity_computes_expr_mean_rate() -> None:
    assert parse_rarity("1/{{#expr:1/( 1/23 * 1/37 ) round 1}}") == (1, 851, None)
    assert parse_rarity("1/{{#expr:1/({{#var:allotseed}}*64) round 1}}") == (
        None,
        None,
        None,
    )


def test_parse_drop_tables_scopes_to_drops_section() -> None:
    drops = parse_drop_tables(_WIKITEXT)
    names = [d.item_name for d in drops]
    assert "Ignored" not in names
    assert "AlsoIgnored" not in names
    assert names == ["Zulrah's scales", "Tanzanite fang", "Flax", "Blood rune"]

    scales = drops[0]
    assert scales.drop_group == "100%"
    assert (scales.quantity_low, scales.quantity_high) == (100, 299)
    assert (scales.rarity_num, scales.rarity_denom) == (1, 1)

    flax = drops[2]
    assert flax.noted is True
    assert flax.rolls == 2
    assert (flax.rarity_num, flax.rarity_denom) == (10, 249)

    blood = drops[3]
    assert blood.drop_group == "Runes"
    assert (blood.rarity_num, blood.rarity_denom) == (None, None)
    assert blood.rarity_text == "Common"


def _source() -> LootSource:
    return LootSource(
        slug="zulrah",
        display_name="Zulrah",
        category="boss",
        wiki_page="Zulrah",
        updated_at=datetime.now(timezone.utc),
    )


def _drop() -> LootDrop:
    return LootDrop(
        id=1,
        source_slug="zulrah",
        item_id=12934,
        item_name="Tanzanite fang",
        quantity_low=1,
        quantity_high=1,
        noted=False,
        rarity_num=1,
        rarity_denom=1024,
        rarity_text=None,
        rolls=2,
        drop_group="Uniques",
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _no_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.reference.loot.prices_for", AsyncMock(return_value={})
    )


async def test_list_sources(anon_client: AsyncClient, mock_session: MagicMock) -> None:
    mock_session.execute.return_value.all.return_value = [(_source(), 48)]
    resp = await anon_client.get("/reference/loot/sources")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["slug"] == "zulrah"
    assert body[0]["category"] == "boss"
    assert body[0]["drop_count"] == 48


async def test_get_source_with_drops(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.get.return_value = _source()
    mock_session.execute.return_value.scalars.return_value.all.return_value = [_drop()]
    resp = await anon_client.get("/reference/loot/sources/zulrah")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == "zulrah"
    assert body["drops"][0]["item_name"] == "Tanzanite fang"
    assert body["drops"][0]["rarity_denom"] == 1024


async def test_get_source_404(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.get.return_value = None
    resp = await anon_client.get("/reference/loot/sources/missing")
    assert resp.status_code == 404


async def test_sources_for_item_reverse_lookup(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.execute.return_value.all.return_value = [(_drop(), _source())]
    resp = await anon_client.get("/reference/loot/items/12934")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["source"]["slug"] == "zulrah"
    assert body[0]["drop"]["item_id"] == 12934
