from __future__ import annotations

from loguru import logger

from app.models.events import LootItem
from app.services.http import OsrsWikiHandler


async def resolve_prices(items: list[LootItem]) -> list[LootItem]:
    """Enrich a list of LootItems with GE prices from the OSRS Wiki prices API.

    Items that cannot be priced (untradeable, fetch failure) are returned unchanged.
    """
    if not items:
        return items

    try:
        wiki = OsrsWikiHandler()
        data = await wiki.get_latest_prices([item.item_id for item in items])
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
