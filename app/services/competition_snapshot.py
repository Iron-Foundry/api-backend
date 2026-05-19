"""Background service that periodically snapshots competition top-5 progress to DB."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.db.models import CompetitionSnapshot, Config
from app.services.http import WiseOldManHandler

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_GLOBAL_GUILD_ID = 0
_COMP_METRIC_MAP_KEY = "competition_metric_map"

POLL_INTERVAL = 1800  # 30 minutes


class CompetitionSnapshotService:
    """Snapshots ongoing competition top-5 progress to DB every 30 minutes."""

    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
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

        snapshots: list[CompetitionSnapshot] = []
        now = datetime.now(timezone.utc)

        async with WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        ) as wom:
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
                metrics: list[str] = metric_map.get(str(comp_id), [])

                for metric in metrics:
                    try:
                        raw = await wom.get_competition_top5_progress(comp_id, metric)
                    except Exception as exc:
                        logger.warning(
                            "CompetitionSnapshotService: WOM fetch failed comp={} metric={} - {}",
                            comp_id,
                            metric,
                            exc,
                        )
                        continue

                    series = [
                        {
                            "player_name": entry["player"]["displayName"],
                            "history": [
                                {
                                    "date": h["date"],
                                    "value": h.get("gained", h.get("value", 0)),
                                }
                                for h in entry.get("history", [])
                            ],
                        }
                        for entry in raw
                        if entry.get("player") and entry.get("history") is not None
                    ]

                    if not series or not any(e["history"] for e in series):
                        logger.debug(
                            "CompetitionSnapshotService: skip empty snapshot comp={} metric={}",
                            comp_id,
                            metric,
                        )
                        continue

                    snapshots.append(
                        CompetitionSnapshot(
                            comp_id=comp_id,
                            metric=metric,
                            captured_at=now,
                            series=series,
                        )
                    )

        if not snapshots:
            return

        async with self._session_factory() as session:
            session.add_all(snapshots)
            await session.commit()

        logger.info(
            "CompetitionSnapshotService: stored {} snapshot(s)",
            len(snapshots),
        )
