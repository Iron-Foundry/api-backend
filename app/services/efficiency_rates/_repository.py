"""Persistence for WOM efficiency rate rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EfficiencyRate

from ._parse import RateRow


async def store_rates(session: AsyncSession, rows: list[RateRow]) -> None:
    """Upsert rate rows keyed by (metric, kind)."""
    if not rows:
        return
    now = datetime.now(timezone.utc)
    for row in rows:
        stmt = pg_insert(EfficiencyRate).values(
            metric=row.metric,
            kind=row.kind,
            rate=row.rate,
            payload=row.payload,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["metric", "kind"],
            set_={
                "rate": stmt.excluded.rate,
                "payload": stmt.excluded.payload,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
    await session.commit()
