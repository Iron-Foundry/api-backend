"""Background service that periodically snapshots competition standings to DB.

Each poll stores the current gained values for top-10 participants per metric.
The overtime endpoint reconstructs the time series from these snapshots.

Competition list is read from the shared Valkey cache written by the competitions
endpoint, avoiding a redundant WOM call. WOM is only hit directly when the cache
is cold.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from valkey.asyncio import Valkey

from app.db.models import CompetitionSnapshot, Config
from app.services.http import WiseOldManHandler

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_GLOBAL_GUILD_ID = 0
_COMP_METRIC_MAP_KEY = "competition_metric_map"

# Mirror of the keys written by the competitions endpoint in clan.py
_COMPS_FRESH_KEY = "clan:competitions_fresh"
_COMPS_STALE_KEY = "clan:competitions_stale"

POLL_INTERVAL = 1800  # 30 minutes


def _safe_gained(v: object) -> float:
    return max(0.0, float(v)) if isinstance(v, (int, float)) else 0.0


class CompetitionSnapshotService:
    """Snapshots ongoing competition standings to DB every 30 minutes.

    Stored series format per row: [{player_name, gained}]
    The overtime endpoint reconstructs the chart series from all stored rows.
    """

    def __init__(self, session_factory, valkey: Valkey) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._valkey = valkey
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="comp-snapshot")
        logger.info("CompetitionSnapshotService started (poll_interval={}s)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CompetitionSnapshotService stopped")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._snapshot_ongoing()
            except Exception as exc:
                logger.warning("CompetitionSnapshotService: error - {}", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _snapshot_ongoing(self) -> None:
        if not self._session_factory:
            return

        async with self._session_factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GLOBAL_GUILD_ID,
                    Config.key == _COMP_METRIC_MAP_KEY,
                )
            )
            metric_map: dict = result.scalar_one_or_none() or {}

        if not metric_map:
            logger.debug("CompetitionSnapshotService: no metric map configured - skipping")
            return

        # Prefer the already-warm Valkey comp cache over a fresh WOM round-trip.
        ongoing: list[dict] = []
        for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
            raw = await self._valkey.get(cache_key)
            if raw:
                comps: list[dict] = json.loads(raw)
                ongoing = [c for c in comps if c.get("status") == "ongoing"]
                logger.debug(
                    "CompetitionSnapshotService: read {} competition(s) from Valkey cache",
                    len(ongoing),
                )
                break

        snapshots: list[CompetitionSnapshot] = []
        now = datetime.now(timezone.utc)

        async with WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        ) as wom:
            if not ongoing:
                # Cache cold - fetch comp list from WOM directly.
                logger.info("CompetitionSnapshotService: Valkey cache cold, fetching from WOM")
                all_comps = await wom.get_all_group_competitions(_WOM_GROUP_ID)
                ongoing = [c for c in all_comps if c.get("status") == "ongoing"]

            if not ongoing:
                logger.debug("CompetitionSnapshotService: no ongoing competitions")
                return

            logger.info(
                "CompetitionSnapshotService: snapshotting {} ongoing competition(s)",
                len(ongoing),
            )

            for comp in ongoing:
                comp_id: int = comp["id"]
                starts_at = datetime.fromisoformat(comp["startsAt"].replace("Z", "+00:00"))
                metrics: list[str] = metric_map.get(str(comp_id), [])

                for metric in metrics:
                    try:
                        data = await wom.get_competition_details(comp_id, metric=metric)
                    except Exception as exc:
                        logger.warning(
                            "CompetitionSnapshotService: WOM fetch failed comp={} metric={} - {}",
                            comp_id,
                            metric,
                            exc,
                        )
                        continue

                    standings = []
                    for p in data.get("participations", []):
                        progress = p.get("progress") or {}
                        standings.append({
                            "player_name": p["player"]["displayName"],
                            "gained": _safe_gained(progress.get("gained")),
                        })

                    standings.sort(key=lambda x: x["gained"], reverse=True)
                    standings = standings[:10]

                    if not standings or all(s["gained"] == 0 for s in standings):
                        logger.debug(
                            "CompetitionSnapshotService: skip - no gains yet comp={} metric={}",
                            comp_id,
                            metric,
                        )
                        continue

                    snapshots.append(
                        CompetitionSnapshot(
                            comp_id=comp_id,
                            metric=metric,
                            captured_at=now,
                            series=standings,
                        )
                    )

                    await self._backfill_start_if_needed(wom, comp_id, metric, starts_at)

        if not snapshots:
            return

        async with self._session_factory() as session:
            session.add_all(snapshots)
            await session.commit()

        logger.info(
            "CompetitionSnapshotService: stored {} snapshot(s) ({})",
            len(snapshots),
            ", ".join(s.metric for s in snapshots),
        )

    async def _backfill_start_if_needed(
        self,
        wom: WiseOldManHandler,
        comp_id: int,
        metric: str,
        starts_at: datetime,
    ) -> None:
        """Insert a t=0 snapshot at competition start if our earliest row postdates it.

        WOM is queried for the participant standings as of ``starts_at`` so the
        chart has a clean baseline anchored to the actual competition start time.
        Skipped if a snapshot already exists within 10 minutes of ``starts_at``.
        """
        async with self._session_factory() as session:
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
            data = await wom.get_competition_details_at(comp_id, metric=metric, date=starts_at)
        except Exception as exc:
            logger.warning(
                "CompetitionSnapshotService: backfill WOM fetch failed comp={} metric={} - {}",
                comp_id,
                metric,
                exc,
            )
            return

        standings = []
        for p in data.get("participations", []):
            standings.append({
                "player_name": p["player"]["displayName"],
                "gained": _safe_gained((p.get("progress") or {}).get("gained")),
            })
        standings.sort(key=lambda x: x["gained"], reverse=True)
        standings = standings[:10]

        async with self._session_factory() as session:
            session.add(
                CompetitionSnapshot(
                    comp_id=comp_id,
                    metric=metric,
                    captured_at=starts_at,
                    series=standings,
                )
            )
            await session.commit()

        logger.info(
            "CompetitionSnapshotService: backfilled start snapshot comp={} metric={} participants={}",
            comp_id,
            metric,
            len(standings),
        )
