from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import UserAccount
from app.services.feed_event import insert_feed_event
from app.services.http import WiseOldManHandler, WomPriority
from app.services.rsn_cascade import backfill_event_user_account, cascade_rsn_change

POLL_INTERVAL = 1800  # 30 minutes


class WomNameChangeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        group_id: int,
        group_key: str | None,
        clan_name: str,
        api_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._group_id = group_id
        self._group_key = group_key
        self._clan_name = clan_name
        self._api_key = api_key
        self._task: asyncio.Task | None = None
        self._last_id: int = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="wom-name-change")
        logger.info("WomNameChangeService started (group_id={})", self._group_id)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("WomNameChangeService stopped")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._process()
            except Exception as exc:
                logger.warning("WomNameChangeService._process error: {}", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _process(self) -> None:
        if self._session_factory is None:
            logger.warning("WomNameChangeService: no session_factory - skipping")
            return

        wom = WiseOldManHandler(
            group_key=self._group_key,
            api_key=self._api_key,
            priority=WomPriority.NORMAL,
        )
        changes: list[dict] = await wom.get_group_name_changes(self._group_id)

        approved = [
            c
            for c in changes
            if c.get("status") == "approved" and c["id"] > self._last_id
        ]
        if not approved:
            logger.debug(
                "WomNameChangeService: no new approved changes (last_id={})",
                self._last_id,
            )
            return

        approved.sort(key=lambda c: c["id"])

        processed = 0
        for change in approved:
            old = change["oldName"]
            new = change["newName"]

            async with self._session_factory() as session:
                result = await session.execute(
                    select(UserAccount.discord_user_id).where(
                        func.lower(UserAccount.rsn) == old.lower()
                    )
                )
                match = result.scalar_one_or_none()

            if not match:
                self._last_id = change["id"]
                continue

            async with self._session_factory() as session:
                await cascade_rsn_change(session, old, new)

            await self._backfill_history(new)

            async with self._session_factory() as session:
                await insert_feed_event(
                    session,
                    type="name_change",
                    player_name=new,
                    user_id=match,
                    data={"old_name": old, "new_name": new},
                )
                await session.commit()

            self._last_id = change["id"]
            processed += 1
            logger.info("WomNameChangeService: cascaded {} -> {}", old, new)

        logger.info(
            "WomNameChangeService: processed {}/{} approved changes",
            processed,
            len(approved),
        )

    async def _backfill_history(self, new_rsn: str) -> None:
        """Fetch WOM name history for new_rsn and overwrite rsn_history + backfill event FKs."""
        try:
            async with WiseOldManHandler(
                api_key=self._api_key, priority=WomPriority.LOW
            ) as wom:
                name_changes = await wom.get_player_name_changes(new_rsn)
        except Exception as exc:
            logger.warning(
                "WomNameChangeService: failed to fetch name history for {}: {}",
                new_rsn,
                exc,
            )
            return

        history = [c["oldName"] for c in name_changes if c.get("status") == "approved"]
        if not history:
            return

        if self._session_factory is None:
            return
        async with self._session_factory() as session:
            ua_result = await session.execute(
                select(UserAccount.id).where(
                    func.lower(UserAccount.rsn) == new_rsn.lower()
                )
            )
            ua_id = ua_result.scalar_one_or_none()
            if not ua_id:
                return

            await session.execute(
                update(UserAccount)
                .where(UserAccount.id == ua_id)
                .values(rsn_history=history)
            )
            await backfill_event_user_account(session, ua_id, [new_rsn] + history)
            await session.commit()

        logger.info(
            "WomNameChangeService: backfilled {} history entries for {}",
            len(history),
            new_rsn,
        )
