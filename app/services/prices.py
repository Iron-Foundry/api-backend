from typing import Any

import httpx
from loguru import logger

from app.models.events import LootItem

WIKI_PRICES_URL = "https://prices.runescape.wiki/api/v1/osrs/latest"
_HEADERS = {"User-Agent": "The Foundry Project - clan event tracker"}


async def resolve_prices(items: list[LootItem]) -> list[LootItem]:
    """Enrich a list of LootItems with GE prices from the OSRS Wiki prices API.

    Items that cannot be priced (untradeable, fetch failure) are returned unchanged.
    """
    if not items:
        return items

    ids = ",".join(str(item.item_id) for item in items)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                WIKI_PRICES_URL,
                params={"id": ids},
                headers=_HEADERS,
                timeout=5.0,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json().get("data", {})
    except Exception as exc:
        logger.warning("Failed to fetch GE prices from wiki: {}", exc)
        return items

    for item in items:
        price_data = data.get(str(item.item_id))
        if not price_data:
            continue
        ge_price: int | None = price_data.get("low") or price_data.get("high")
        if ge_price:
            item.ge_price = ge_price
            item.total_value = ge_price * item.quantity

    return items
