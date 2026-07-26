from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LootDrop, LootSource
from app.dependencies import get_session

from ._helpers import drop_out, prices_for, source_out
from ._schemas import ItemSourceOut, SourceDetailOut, SourceListOut

router = APIRouter(prefix="/loot", tags=["reference"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/sources")
async def list_sources(
    session: SessionDep,
    category: Annotated[str | None, Query()] = None,
) -> list[SourceListOut]:
    stmt = (
        select(LootSource, func.count(LootDrop.id))
        .outerjoin(LootDrop, LootDrop.source_slug == LootSource.slug)
        .group_by(LootSource.slug)
        .order_by(LootSource.display_name)
    )
    if category:
        stmt = stmt.where(LootSource.category == category)
    rows = (await session.execute(stmt)).all()
    return [
        SourceListOut(**source_out(source).model_dump(), drop_count=count)
        for source, count in rows
    ]


@router.get("/sources/{slug}")
async def get_source(slug: str, session: SessionDep) -> SourceDetailOut:
    source = await session.get(LootSource, slug)
    if source is None:
        raise HTTPException(status_code=404, detail="Loot source not found")
    drops = (
        (
            await session.execute(
                select(LootDrop)
                .where(LootDrop.source_slug == slug)
                .order_by(LootDrop.id)
            )
        )
        .scalars()
        .all()
    )
    prices = await prices_for([d.item_id for d in drops if d.item_id])
    return SourceDetailOut(
        **source_out(source).model_dump(),
        drops=[drop_out(drop, prices) for drop in drops],
    )


@router.get("/items/{item_id}")
async def sources_for_item(
    item_id: Annotated[int, Path(ge=0)], session: SessionDep
) -> list[ItemSourceOut]:
    stmt = (
        select(LootDrop, LootSource)
        .join(LootSource, LootDrop.source_slug == LootSource.slug)
        .where(LootDrop.item_id == item_id)
        .order_by(LootSource.display_name)
    )
    rows = (await session.execute(stmt)).all()
    prices = await prices_for([item_id])
    return [
        ItemSourceOut(source=source_out(source), drop=drop_out(drop, prices))
        for drop, source in rows
    ]
