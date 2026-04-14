# DEPRECATED — MongoDB implementation. Kept for reference. Not imported in production.
from __future__ import annotations

import asyncio
import re

import httpx
from loguru import logger

from app.services.rsn_cascade import cascade_rsn_change

WOM_BASE = "https://api.wiseoldman.net/v2"
POLL_INTERVAL = 1800  # 30 minutes


class WomNameChangeService:
    def __init__(self, db, group_id: int, group_key: str | None, clan_name: str) -> None:  # type: ignore[no-untyped-def]
        self._db = db
        self._group_id = group_id
        self._group_key = group_key
        self._clan_name = clan_name
        self._task: asyncio.Task | None = None

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
        cursor_doc = await self._db["service_cursors"].find_one({"_id": "wom_name_change_cursor"})
        last_id: int = cursor_doc["last_id"] if cursor_doc else 0

        headers: dict[str, str] = {}
        if self._group_key:
            headers["x-wom-group-token"] = self._group_key

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{WOM_BASE}/groups/{self._group_id}/name-changes",
                params={"limit": 100},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            changes: list[dict] = resp.json()

        approved = [c for c in changes if c.get("status") == "approved" and c["id"] > last_id]
        if not approved:
            logger.debug("WomNameChangeService: no new approved changes (last_id={})", last_id)
            return

        approved.sort(key=lambda c: c["id"])

        processed = 0
        for change in approved:
            old = change["oldName"]
            new = change["newName"]

            match = await self._db["users"].find_one(
                {"rsn": {"$regex": f"^{re.escape(old)}$", "$options": "i"}}
            )
            if not match:
                await self._db["service_cursors"].update_one(
                    {"_id": "wom_name_change_cursor"},
                    {"$set": {"last_id": change["id"]}},
                    upsert=True,
                )
                last_id = change["id"]
                continue

            await cascade_rsn_change(self._db, old, new, self._clan_name)
            await self._db["service_cursors"].update_one(
                {"_id": "wom_name_change_cursor"},
                {"$set": {"last_id": change["id"]}},
                upsert=True,
            )
            last_id = change["id"]
            processed += 1
            logger.info("WomNameChangeService: cascaded {} → {}", old, new)

        logger.info(
            "WomNameChangeService: processed {}/{} approved changes",
            processed,
            len(approved),
        )
