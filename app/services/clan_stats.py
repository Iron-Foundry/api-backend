"""Hourly background service that fetches WOM clan stats and persists them to DB."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ClanStats
from app.services.clan_rank_sync import sync_wom_ranks
from app.services.http import WiseOldManHandler, WomPriority

POLL_INTERVAL = 3600  # 1 hour

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")

RAID_METRICS: dict[str, tuple[str, ...]] = {
    "cox_kc": ("chambers_of_xeric", "chambers_of_xeric_challenge_mode"),
    "tob_kc": ("theatre_of_blood", "theatre_of_blood_hard_mode"),
    "toa_kc": ("tombs_of_amascut", "tombs_of_amascut_expert_mode"),
    "tfa_kc": ("the_fractured_archive",),
}


def raid_kc_totals(bulk_entries: list[dict[str, Any]]) -> dict[str, int]:
    """Return the clan's summed kills per raid column from WOM bulk hiscores."""
    totals = dict.fromkeys(RAID_METRICS, 0)
    for entry in bulk_entries:
        bosses: dict[str, Any] = ((entry.get("data") or {}).get("data") or {}).get(
            "bosses"
        ) or {}
        for column, metrics in RAID_METRICS.items():
            for metric in metrics:
                kills = (bosses.get(metric) or {}).get("kills")
                totals[column] += kills if isinstance(kills, int) and kills > 0 else 0
    return totals


class ClanStatsService:
    """Refreshes clan_stats (id=1) every hour from WiseOldMan."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="clan-stats-refresh")
        logger.info("ClanStatsService started (poll_interval={}s)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("ClanStatsService stopped")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._refresh()
            except Exception as exc:
                logger.warning("ClanStatsService._refresh error: {}", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _refresh(self) -> None:
        if self._session_factory is None:
            logger.warning("ClanStatsService: no session_factory - skipping")
            return

        logger.info("ClanStatsService: fetching WOM stats (group={})", _WOM_GROUP_ID)

        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.LOW,
        ) as wom:
            group_result, bulk_result = await asyncio.gather(
                wom.get_group(_WOM_GROUP_ID),
                wom.get_group_bulk_hiscores(_WOM_GROUP_ID),
                return_exceptions=True,
            )

        if isinstance(group_result, BaseException):
            logger.warning("ClanStatsService: WOM fetch failed: {}", group_result)
            return

        raw: dict[str, Any] = group_result
        memberships = raw.get("memberships") or []
        raids = raid_kc_totals(bulk_result if isinstance(bulk_result, list) else [])

        member_count = raw.get("memberCount", 0)
        total_xp = sum(m.get("player", {}).get("exp", 0) for m in memberships)
        total_ehb = round(sum(m.get("player", {}).get("ehb", 0.0) for m in memberships))

        stmt = pg_insert(ClanStats).values(
            id=1,
            member_count=member_count,
            total_xp=total_xp,
            total_ehb=total_ehb,
            **raids,
            updated_at=datetime.now(UTC),
        )
        columns = ["member_count", "total_xp", "total_ehb", *raids, "updated_at"]
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c: stmt.excluded[c] for c in columns},
        )

        async with self._session_factory() as session:
            await session.execute(stmt)
            await session.commit()

        logger.info(
            "ClanStatsService: updated - members={}, total_xp={:,}, raids={}",
            member_count,
            total_xp,
            raids,
        )

        await sync_wom_ranks(self._session_factory, memberships)
