"""Background service that closes expired parties every 60 seconds."""

from __future__ import annotations

import asyncio

from loguru import logger


class PartyExpiryService:
    """Polls for expired parties and closes them every 60 seconds."""

    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="party-expiry")
        logger.info("PartyExpiryService started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PartyExpiryService stopped")

    async def _run(self) -> None:
        from app.party_store import expire_parties
        from app.services.discord_party import close_party_embed

        while True:
            await asyncio.sleep(60)
            if not self._session_factory:
                continue
            try:
                async with self._session_factory() as session:
                    for party in await expire_parties(session):
                        logger.info(
                            "PartyExpiryService: closing expired party {}", party.id
                        )
                        await close_party_embed(party)
            except Exception as exc:
                logger.warning("PartyExpiryService: error - {}", exc)
