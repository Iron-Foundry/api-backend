"""Service for fetching and storing WOM group bulk gains snapshots."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.gains import BulkGainsBatch, PlayerBulkGains
from app.services.http.wom import WiseOldManHandler
from app.services.http.wom_queue import WomPriority
from ._parse import parse_bulk_gains_data

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")


class BulkGainsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def fetch_and_store(
        self,
        *,
        period: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        """Fetch bulk gains from WOM and persist to DB. Returns the count of players stored."""
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.NORMAL,
        ) as wom:
            raw = await wom.get_group_bulk_gains(
                _WOM_GROUP_ID,
                period=period,
                start_date=start_date,
                end_date=end_date,
            )

        if not raw:
            logger.warning("BulkGainsService: WOM returned empty bulk-gained response")
            return 0

        now = datetime.now(timezone.utc)
        batch = BulkGainsBatch(
            period=period,
            start_date=start_date,
            end_date=end_date,
            captured_at=now,
        )

        player_rows: list[PlayerBulkGains] = []
        for entry in raw:
            player = entry.get("player", {})
            rsn: str = player.get("username", "").lower()
            if not rsn:
                continue
            gains_start_raw: str | None = entry.get("startDate")
            gains_end_raw: str | None = entry.get("endDate")
            if not gains_start_raw or not gains_end_raw:
                continue
            gains_start = datetime.fromisoformat(gains_start_raw.replace("Z", "+00:00"))
            gains_end = datetime.fromisoformat(gains_end_raw.replace("Z", "+00:00"))
            skills, bosses, activities = parse_bulk_gains_data(entry.get("data", []))
            player_rows.append(
                PlayerBulkGains(
                    rsn=rsn,
                    gains_start=gains_start,
                    gains_end=gains_end,
                    skills=skills,
                    bosses=bosses,
                    activities=activities,
                )
            )

        async with self._session_factory() as session:
            session.add(batch)
            await session.flush()
            for row in player_rows:
                row.batch_id = batch.id
            session.add_all(player_rows)
            await session.commit()

        logger.info(
            "BulkGainsService: stored batch {} with {} player rows",
            batch.id,
            len(player_rows),
        )
        return len(player_rows)

    async def find_batch_for_range(
        self, start_date: datetime, end_date: datetime
    ) -> BulkGainsBatch | None:
        """Find the most recent batch whose date range covers the given interval."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(BulkGainsBatch)
                .where(
                    BulkGainsBatch.start_date.is_not(None),
                    BulkGainsBatch.end_date.is_not(None),
                    BulkGainsBatch.start_date <= start_date,
                    BulkGainsBatch.end_date >= end_date,
                )
                .order_by(BulkGainsBatch.captured_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_player_gains(self, batch_id: int, rsn: str) -> PlayerBulkGains | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerBulkGains).where(
                    PlayerBulkGains.batch_id == batch_id,
                    PlayerBulkGains.rsn == rsn.lower(),
                )
            )
            return result.scalar_one_or_none()

    async def get_batch_players(self, batch_id: int) -> list[PlayerBulkGains]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerBulkGains)
                .where(PlayerBulkGains.batch_id == batch_id)
                .order_by(PlayerBulkGains.rsn)
            )
            return list(result.scalars().all())

    async def list_batches(self, limit: int = 20) -> list[BulkGainsBatch]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(BulkGainsBatch)
                .order_by(BulkGainsBatch.captured_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
