from __future__ import annotations

from loguru import logger

from app.db.models import LootDrop, LootSource
from app.services.http import OsrsWikiHandler

from ._schemas import DropOut, SourceOut


async def prices_for(item_ids: list[int]) -> dict[int, int]:
    """Fetch current GE prices for the given item ids, keyed by id."""
    ids = [i for i in dict.fromkeys(item_ids) if i]
    if not ids:
        return {}
    try:
        data = await OsrsWikiHandler().get_latest_prices(ids)
    except Exception as exc:
        logger.warning("reference: GE price fetch failed: {}", exc)
        return {}
    prices: dict[int, int] = {}
    for raw_id, entry in data.items():
        value = entry.get("high") or entry.get("low")
        if value:
            prices[int(raw_id)] = value
    return prices


def source_out(source: LootSource) -> SourceOut:
    return SourceOut(
        slug=source.slug,
        display_name=source.display_name,
        category=source.category,
        wiki_page=source.wiki_page,
        reward_kind=source.reward_kind,
        updated_at=source.updated_at,
    )


def drop_out(drop: LootDrop, prices: dict[int, int]) -> DropOut:
    return DropOut(
        item_id=drop.item_id,
        item_name=drop.item_name,
        quantity_low=drop.quantity_low,
        quantity_high=drop.quantity_high,
        noted=drop.noted,
        rarity_num=drop.rarity_num,
        rarity_denom=drop.rarity_denom,
        rarity_text=drop.rarity_text,
        rolls=drop.rolls,
        drop_group=drop.drop_group,
        ge_price=prices.get(drop.item_id) if drop.item_id else None,
    )
