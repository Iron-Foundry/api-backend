"""Hourly background service that fetches WOM clan stats and persists them to DB."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from typing import cast

from loguru import logger
from sqlalchemy import ARRAY, Text, bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ClanStats
from app.services.http import WiseOldManHandler, WomPriority

POLL_INTERVAL = 3600  # 1 hour

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")

_RAID_METRICS = [
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert_mode",
]


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
            try:
                await self._task
            except asyncio.CancelledError:
                pass
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
            group_data, *raid_totals = await asyncio.gather(
                wom.get_group(_WOM_GROUP_ID),
                *[wom.fetch_metric_total(_WOM_GROUP_ID, m) for m in _RAID_METRICS],
                return_exceptions=True,
            )

        if isinstance(group_data, BaseException):
            logger.warning("ClanStatsService: WOM fetch failed: {}", group_data)
            return

        assert isinstance(group_data, dict)
        raw: dict = group_data
        memberships = raw.get("memberships") or []

        def _safe_int(v: object) -> int:
            return v if isinstance(v, int) else 0

        metric_totals = {m: _safe_int(t) for m, t in zip(_RAID_METRICS, raid_totals)}

        member_count = raw.get("memberCount", 0)
        total_xp = sum(m.get("player", {}).get("exp", 0) for m in memberships)
        total_ehb = round(sum(m.get("player", {}).get("ehb", 0.0) for m in memberships))
        cox_kc = (
            metric_totals["chambers_of_xeric"]
            + metric_totals["chambers_of_xeric_challenge_mode"]
        )
        tob_kc = (
            metric_totals["theatre_of_blood"]
            + metric_totals["theatre_of_blood_hard_mode"]
        )
        toa_kc = (
            metric_totals["tombs_of_amascut"]
            + metric_totals["tombs_of_amascut_expert_mode"]
        )

        stmt = pg_insert(ClanStats).values(
            id=1,
            member_count=member_count,
            total_xp=total_xp,
            total_ehb=total_ehb,
            cox_kc=cox_kc,
            tob_kc=tob_kc,
            toa_kc=toa_kc,
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "member_count": stmt.excluded.member_count,
                "total_xp": stmt.excluded.total_xp,
                "total_ehb": stmt.excluded.total_ehb,
                "cox_kc": stmt.excluded.cox_kc,
                "tob_kc": stmt.excluded.tob_kc,
                "toa_kc": stmt.excluded.toa_kc,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        async with self._session_factory() as session:
            await session.execute(stmt)
            await session.commit()

        logger.info(
            "ClanStatsService: updated - members={}, total_xp={:,}, cox={} tob={} toa={}",
            member_count,
            total_xp,
            cox_kc,
            tob_kc,
            toa_kc,
        )

        await _sync_wom_ranks(self._session_factory, memberships)


async def _sync_wom_ranks(
    session_factory: async_sessionmaker[AsyncSession], memberships: list[dict]
) -> None:
    """Bulk-write WOM in-game ranks to users.clan_rank for all matched members."""
    wom_ranks: dict[str, str] = {
        m["player"]["username"].lower(): m["role"]
        for m in memberships
        if m.get("player") and m.get("role")
    }
    if not wom_ranks:
        return

    rsns = list(wom_ranks.keys())
    roles = list(wom_ranks.values())

    _arr = ARRAY(Text())
    _params = [bindparam("rsns", type_=_arr), bindparam("roles", type_=_arr)]

    async with session_factory() as session:
        r1 = cast(
            CursorResult,
            await session.execute(
                text("""
                UPDATE users u
                   SET clan_rank  = wd.role,
                       updated_at = now()
                  FROM (SELECT unnest(:rsns) AS rsn,
                               unnest(:roles) AS role) AS wd
                  JOIN user_accounts ua ON lower(ua.rsn) = wd.rsn
                 WHERE ua.discord_user_id = u.discord_user_id
                   AND (u.clan_rank IS DISTINCT FROM wd.role)
            """).bindparams(*_params),
                {"rsns": rsns, "roles": roles},
            ),
        )
        r2 = cast(
            CursorResult,
            await session.execute(
                text("""
                UPDATE users u
                   SET clan_rank  = wd.role,
                       updated_at = now()
                  FROM (SELECT unnest(:rsns) AS rsn,
                               unnest(:roles) AS role) AS wd
                 WHERE lower(u.rsn) = wd.rsn
                   AND (u.clan_rank IS DISTINCT FROM wd.role)
            """).bindparams(*_params),
                {"rsns": rsns, "roles": roles},
            ),
        )
        await session.commit()

    logger.info(
        "WOM rank sync: updated {} (user_accounts) + {} (legacy rsn)",
        r1.rowcount,
        r2.rowcount,
    )
