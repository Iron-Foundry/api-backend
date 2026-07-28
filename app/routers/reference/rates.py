from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EfficiencyRate
from app.dependencies import get_session

from ._schemas import RateOut

router = APIRouter(prefix="/rates")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_rates(
    session: SessionDep,
    kind: Annotated[str | None, Query(pattern="^(ehp|ehb)$")] = None,
) -> list[RateOut]:
    """List WiseOldMan efficiency rates, filtered to EHP or EHB."""
    stmt = select(EfficiencyRate).order_by(EfficiencyRate.metric)
    if kind:
        stmt = stmt.where(EfficiencyRate.kind == kind)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        RateOut(
            metric=row.metric,
            kind=row.kind,
            rate=row.rate,
            payload=row.payload,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
