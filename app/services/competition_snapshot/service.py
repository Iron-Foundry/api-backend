"""Background service that periodically snapshots competition standings to DB."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from valkey.asyncio import Valkey

from app.db.models import CompetitionSnapshot, Config
from app.services.http import WiseOldManHandler, WomPriority
from ._fetch import backfill_start_if_needed, fetch_metric_standings, load_ongoing_comps

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_GLOBAL_GUILD_ID = 0
_COMP_METRIC_MAP_KEY = "competition_metric_map"
POLL_INTERVAL = 1800  # 30 minutes


class CompetitionSnapshotService:
    """Snapshots ongoing competition standings to DB every 30 minutes."""

    def __init__(self, session_factory, valkey: Valkey) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._valkey = valkey
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

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
                select(Config.value).where(Config.guild_id == _GLOBAL_GUILD_ID, Config.key == _COMP_METRIC_MAP_KEY)
            )
            metric_map: dict = result.scalar_one_or_none() or {}

        if not metric_map:
            logger.debug("CompetitionSnapshotService: no metric map configured - skipping")
            return

        snapshots: list[CompetitionSnapshot] = []
        now = datetime.now(timezone.utc)

        async with WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, priority=WomPriority.NORMAL) as wom:
            ongoing = await load_ongoing_comps(self._valkey, wom, _WOM_GROUP_ID)

            if not ongoing:
                logger.debug("CompetitionSnapshotService: no ongoing competitions")
                return

            logger.info("CompetitionSnapshotService: snapshotting {} ongoing competition(s)", len(ongoing))

            for comp in ongoing:
                comp_id: int = comp["id"]
                starts_at = datetime.fromisoformat(comp["startsAt"].replace("Z", "+00:00"))
                metrics: list[str] = metric_map.get(str(comp_id), [])

                for metric in metrics:
                    standings = await fetch_metric_standings(wom, comp_id, metric)
                    if standings is None:
                        continue
                    snapshots.append(CompetitionSnapshot(comp_id=comp_id, metric=metric, captured_at=now, series=standings))
                    await backfill_start_if_needed(self._session_factory, wom, comp_id, metric, starts_at)

        if not snapshots:
            return

        async with self._session_factory() as session:
            session.add_all(snapshots)
            await session.commit()

        logger.info("CompetitionSnapshotService: stored {} snapshot(s) ({})", len(snapshots), ", ".join(s.metric for s in snapshots))
