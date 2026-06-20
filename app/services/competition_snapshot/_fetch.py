"""Standalone fetch helpers for the competition snapshot service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select
from valkey.asyncio import Valkey

from app.db.models import CompetitionSnapshot
from app.services.http import WiseOldManHandler

_COMPS_FRESH_KEY = "clan:competitions_fresh"
_COMPS_STALE_KEY = "clan:competitions_stale"


def _safe_gained(v: object) -> float:
    return max(0.0, float(v)) if isinstance(v, (int, float)) else 0.0


async def load_ongoing_comps(
    valkey: Valkey, wom: WiseOldManHandler, wom_group_id: str
) -> list[dict]:
    """Return ongoing competitions from Valkey cache, falling back to WOM."""
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            ongoing = [c for c in comps if c.get("status") == "ongoing"]
            logger.debug(
                "CompetitionSnapshotService: {} competition(s) from Valkey cache",
                len(ongoing),
            )
            return ongoing

    logger.info("CompetitionSnapshotService: Valkey cache cold, fetching from WOM")
    all_comps = await wom.get_all_group_competitions(wom_group_id)
    return [c for c in all_comps if c.get("status") == "ongoing"]


async def fetch_metric_standings(
    wom: WiseOldManHandler, comp_id: int, metric: str
) -> list[dict] | None:
    """Fetch top-10 standings for a single (comp_id, metric) from WOM."""
    try:
        data = await wom.get_competition_details(comp_id, metric=metric)
    except Exception as exc:
        logger.warning(
            "CompetitionSnapshotService: WOM fetch failed comp={} metric={} - {}",
            comp_id,
            metric,
            exc,
        )
        return None

    standings = sorted(
        [
            {
                "player_name": p["player"]["displayName"],
                "gained": _safe_gained((p.get("progress") or {}).get("gained")),
            }
            for p in data.get("participations", [])
        ],
        key=lambda x: x["gained"],
        reverse=True,
    )[:10]

    if not standings or all(s["gained"] == 0 for s in standings):
        logger.debug(
            "CompetitionSnapshotService: skip - no gains yet comp={} metric={}",
            comp_id,
            metric,
        )
        return None

    return standings


async def backfill_start_if_needed(
    session_factory,  # type: ignore[no-untyped-def]
    wom: WiseOldManHandler,
    comp_id: int,
    metric: str,
    starts_at: datetime,
) -> None:
    """Insert a t=0 snapshot at competition start if our earliest row postdates it."""
    async with session_factory() as session:
        result = await session.execute(
            select(CompetitionSnapshot.captured_at)
            .where(
                CompetitionSnapshot.comp_id == comp_id,
                CompetitionSnapshot.metric == metric,
            )
            .order_by(CompetitionSnapshot.captured_at.asc())
            .limit(1)
        )
        earliest_at: datetime | None = result.scalar_one_or_none()

    if earliest_at is not None and (earliest_at - starts_at) < timedelta(minutes=10):
        return

    logger.info(
        "CompetitionSnapshotService: backfilling start snapshot comp={} metric={} starts_at={}",
        comp_id,
        metric,
        starts_at.isoformat(),
    )

    try:
        data = await wom.get_competition_details_at(
            comp_id, metric=metric, date=starts_at
        )
    except Exception as exc:
        logger.warning(
            "CompetitionSnapshotService: backfill WOM fetch failed comp={} metric={} - {}",
            comp_id,
            metric,
            exc,
        )
        return

    standings = [
        {"player_name": p["player"]["displayName"], "gained": 0.0}
        for p in data.get("participations", [])
    ][:10]

    async with session_factory() as session:
        session.add(
            CompetitionSnapshot(
                comp_id=comp_id, metric=metric, captured_at=starts_at, series=standings
            )
        )
        await session.commit()

    logger.info(
        "CompetitionSnapshotService: backfilled start snapshot comp={} metric={} participants={}",
        comp_id,
        metric,
        len(standings),
    )
