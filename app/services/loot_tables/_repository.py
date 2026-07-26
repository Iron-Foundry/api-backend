"""Persistence for loot sources and their drop tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LootDrop, LootSource

from ._catalog import LootSourceEntry
from ._drops import ParsedDrop
from ._items import resolve_item_id


async def store_source_drops(
    session: AsyncSession,
    entry: LootSourceEntry,
    drops: list[ParsedDrop],
    item_index: dict[str, int],
) -> None:
    """Upsert one source row and replace its full drop table in one transaction."""
    now = datetime.now(timezone.utc)

    stmt = pg_insert(LootSource).values(
        slug=entry.slug,
        display_name=entry.display_name,
        category=entry.category,
        wiki_page=entry.wiki_page,
        reward_kind=entry.reward_kind,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "display_name": stmt.excluded.display_name,
            "category": stmt.excluded.category,
            "wiki_page": stmt.excluded.wiki_page,
            "reward_kind": stmt.excluded.reward_kind,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)

    await session.execute(delete(LootDrop).where(LootDrop.source_slug == entry.slug))

    await _insert_drops(session, entry.slug, drops, item_index, now)
    await session.commit()


async def prune_sources(session: AsyncSession, keep: set[str]) -> None:
    """Delete loot sources no longer in the catalog (cascades to their drops)."""
    existing = set((await session.execute(select(LootSource.slug))).scalars().all())
    stale = existing - keep
    if not stale:
        return
    await session.execute(delete(LootSource).where(LootSource.slug.in_(stale)))
    await session.commit()


async def _insert_drops(
    session: AsyncSession,
    slug: str,
    drops: list[ParsedDrop],
    item_index: dict[str, int],
    now: datetime,
) -> None:
    if not drops:
        return
    session.add_all(
        [
            LootDrop(
                source_slug=slug,
                item_id=resolve_item_id(drop.item_name, item_index),
                item_name=drop.item_name,
                quantity_low=drop.quantity_low,
                quantity_high=drop.quantity_high,
                noted=drop.noted,
                rarity_num=drop.rarity_num,
                rarity_denom=drop.rarity_denom,
                rarity_text=drop.rarity_text,
                rolls=drop.rolls,
                drop_group=drop.drop_group,
                updated_at=now,
            )
            for drop in drops
        ]
    )
