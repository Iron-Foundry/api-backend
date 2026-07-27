"""Hourly background service that syncs ironman EHP/EHB rates from WiseOldMan."""

from __future__ import annotations

import asyncio
import contextlib
import os

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.http import WiseOldManHandler, WomPriority

from ._parse import parse_ehb, parse_ehp
from ._repository import store_rates

POLL_INTERVAL = 3600
_ACCOUNT_TYPE = "ironman"

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")


class EfficiencyRatesService:
    """Refreshes efficiency_rates hourly from WiseOldMan (ironman rates)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="efficiency-rates")
        logger.info("EfficiencyRatesService started (poll_interval={}s)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("EfficiencyRatesService stopped")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._refresh()
            except Exception as exc:
                logger.warning("EfficiencyRatesService._refresh error: {}", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _refresh(self) -> None:
        if self._session_factory is None:
            logger.warning("EfficiencyRatesService: no session_factory - skipping")
            return

        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.LOW,
        ) as wom:
            ehb_raw = await wom.get_efficiency_rates("ehb", _ACCOUNT_TYPE)
            ehp_raw = await wom.get_efficiency_rates("ehp", _ACCOUNT_TYPE)

        rows = parse_ehb(ehb_raw) + parse_ehp(ehp_raw)
        async with self._session_factory() as session:
            await store_rates(session, rows)

        logger.info("EfficiencyRatesService: stored {} rate rows", len(rows))


__all__ = ["EfficiencyRatesService"]
