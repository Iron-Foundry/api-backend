from __future__ import annotations

import asyncio

from loguru import logger

from app.services.feed_event import insert_feed_event
from app.services.http import WiseOldManHandler, WomPriority
from app.services.rsn_cascade import cascade_rsn_change

POLL_INTERVAL = 1800  # 30 minutes


class WomNameChangeService:
    def __init__(
        self,
        session_factory,  # type: ignore[no-untyped-def]
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

            from sqlalchemy import func, select

            from app.db.models import UserAccount

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
            logger.info("WomNameChangeService: cascaded {} → {}", old, new)

        logger.info(
            "WomNameChangeService: processed {}/{} approved changes",
            processed,
            len(approved),
        )
