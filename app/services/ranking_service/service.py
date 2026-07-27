"""Background service that fetches WOM player snapshots and ranks the clan."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Config, PlayerRanking, PlayerSnapshot, UserAccount
from app.services.http.wom import WiseOldManHandler
from app.services.http.wom_queue import WomPriority

from .config import (
    _DEFAULT_CONFIG,
    _GLOBAL_GUILD_ID,
    _RANKING_CONFIG_KEY,
    _WOM_DISCORD_CONTACT,
    POLL_INTERVAL,
)
from .scoring import RankingConfig, rank_from_snapshots


class RankingService:
    """Fetches WOM player snapshots and ranks the clan once per hour."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        group_id: int,
        api_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._group_id = group_id
        self._api_key = api_key
        self._task: asyncio.Task[None] | None = None
        self._run_event = asyncio.Event()
        self._run_active: bool = False
        self.last_run_at: datetime | None = None
        self.last_run_count: int = 0
        self.last_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def run_active(self) -> bool:
        return self._run_active

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="ranking-service")
        logger.info(
            "RankingService started (group_id={}, poll_interval={}s)",
            self._group_id,
            POLL_INTERVAL,
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("RankingService stopped")

    def run_now(self) -> bool:
        """Trigger an immediate ranking run. Returns False if already running."""
        if self._run_active:
            return False
        self._run_event.set()
        return True

    async def _poll_loop(self) -> None:
        while True:
            self._run_event.clear()
            self._run_active = True
            try:
                await self._refresh()
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("RankingService._refresh error: {}", exc)
            finally:
                self._run_active = False
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._run_event.wait(), timeout=POLL_INTERVAL)

    async def _get_config(self) -> RankingConfig:
        if self._session_factory is None:
            return _DEFAULT_CONFIG
        async with self._session_factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GLOBAL_GUILD_ID,
                    Config.key == _RANKING_CONFIG_KEY,
                )
            )
            stored = result.scalar_one_or_none()
        if not stored or stored.get("version") != 2:
            logger.warning("ranking_config missing or pre-v2 - using defaults")
            return _DEFAULT_CONFIG
        try:
            return RankingConfig.from_dict(stored)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("ranking_config parse error: {} - using defaults", exc)
            return _DEFAULT_CONFIG

    async def _refresh(self) -> None:
        if self._session_factory is None:
            logger.warning("RankingService: no session_factory - skipping")
            return

        config = await self._get_config()
        logger.info("RankingService: fetching group {} from WOM", self._group_id)

        async with WiseOldManHandler(
            api_key=self._api_key,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.LOW,
        ) as wom:
            logger.info(
                "RankingService: fetching bulk hiscores for group {}", self._group_id
            )
            bulk = await wom.get_group_bulk_hiscores(self._group_id)

        logger.info(
            "RankingService: received {} player entries from bulk hiscores", len(bulk)
        )

        now = datetime.now(UTC)
        cleaned: list[dict[str, Any]] = []
        snapshot_rows = []
        skill_names = {m.name for m in config.skills}

        for entry in bulk:
            player = entry.get("player", {})
            rsn = player.get("username", "").lower()
            if not rsn:
                continue
            snapshot_data = entry.get("data")
            if not snapshot_data:
                continue
            data = snapshot_data.get("data", {})
            skills = {
                n: float(info.get("experience", 0) if isinstance(info, dict) else info)
                for n, info in data.get("skills", {}).items()
                if n in skill_names
            }
            bosses = {
                n: int(info.get("kills", 0) if isinstance(info, dict) else info)
                for n, info in data.get("bosses", {}).items()
            }
            activities = {
                n: int(info.get("score", 0) if isinstance(info, dict) else info)
                for n, info in data.get("activities", {}).items()
            }
            cleaned.append({"rsn": rsn, "skills": skills, "bosses": bosses})
            snapshot_rows.append(
                {
                    "rsn": rsn,
                    "skills": skills,
                    "bosses": bosses,
                    "activities": activities,
                    "fetched_at": now,
                }
            )

        ranked = rank_from_snapshots(cleaned, config)

        async with self._session_factory() as session:
            rsn_map_result = await session.execute(
                select(UserAccount.discord_user_id, UserAccount.rsn)
            )
            rsn_to_user: dict[str, int] = {
                row.rsn.lower(): row.discord_user_id for row in rsn_map_result
            }

            if snapshot_rows:
                snap_stmt = pg_insert(PlayerSnapshot).values(snapshot_rows)
                await session.execute(
                    snap_stmt.on_conflict_do_update(
                        index_elements=["rsn"],
                        set_={
                            "skills": snap_stmt.excluded.skills,
                            "bosses": snap_stmt.excluded.bosses,
                            "activities": snap_stmt.excluded.activities,
                            "fetched_at": snap_stmt.excluded.fetched_at,
                        },
                    )
                )

            ranking_rows = [
                {
                    "rsn": r["rsn"],
                    "rank": r["rank"],
                    "points": r["points"],
                    "boss_points": r["boss_points"],
                    "skill_points": r["skill_points"],
                    "discord_user_id": rsn_to_user.get(r["rsn"]),
                    "updated_at": now,
                }
                for r in ranked
            ]
            if ranking_rows:
                rank_stmt = pg_insert(PlayerRanking).values(ranking_rows)
                await session.execute(
                    rank_stmt.on_conflict_do_update(
                        index_elements=["rsn"],
                        set_={
                            "rank": rank_stmt.excluded.rank,
                            "points": rank_stmt.excluded.points,
                            "boss_points": rank_stmt.excluded.boss_points,
                            "skill_points": rank_stmt.excluded.skill_points,
                            "discord_user_id": rank_stmt.excluded.discord_user_id,
                            "updated_at": rank_stmt.excluded.updated_at,
                        },
                    )
                )
            await session.commit()

        self.last_run_at = now
        self.last_run_count = len(ranked)
        self.last_error = None
        logger.info("RankingService: ranked {} players", len(ranked))

    async def rank_from_config(
        self, config_override: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Re-rank using stored snapshots and a given config dict. No DB writes."""
        if self._session_factory is None:
            return []
        if config_override.get("version") == 2:
            try:
                config = RankingConfig.from_dict(config_override)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("rank_from_config parse error: {} - using defaults", exc)
                config = _DEFAULT_CONFIG
        else:
            config = _DEFAULT_CONFIG
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerSnapshot.rsn, PlayerSnapshot.skills, PlayerSnapshot.bosses)
            )
            snapshots = [
                {"rsn": row.rsn, "skills": row.skills, "bosses": row.bosses}
                for row in result
            ]
        return rank_from_snapshots(snapshots, config)
