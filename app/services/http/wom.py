"""WiseOldMan API handler with smart in-memory competition cache."""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from app.services.http.base import BaseRequestHandler
from app.services.http.wom_queue import WomPriority, get_wom_queue
from .wom_competition import WomCompetitionMixin
from .wom_group import WomGroupMixin
from .wom_player import WomPlayerMixin


class WiseOldManHandler(
    WomCompetitionMixin, WomGroupMixin, WomPlayerMixin, BaseRequestHandler
):
    base_url = "https://api.wiseoldman.net/v2"
    default_timeout = 30.0

    def __init__(
        self,
        *,
        api_key: str | None = None,
        discord_contact: str | None = None,
        group_key: str | None = None,
        timeout: float | None = None,
        priority: WomPriority = WomPriority.NORMAL,
    ) -> None:
        super().__init__(timeout=timeout)
        self._group_key = group_key
        self._priority = priority

        user_agent = (
            f"IronFoundry/1.0 (discord: @{discord_contact})"
            if discord_contact
            else "IronFoundry/1.0"
        )
        headers: dict[str, str] = {"User-Agent": user_agent}
        if api_key:
            headers["x-api-key"] = api_key
        if group_key:
            headers["x-wom-group-token"] = group_key

        self.default_headers = headers  # type: ignore[assignment]

    async def _get_with_rate_limit(
        self, path: str, *, params: dict | None = None
    ) -> httpx.Response:
        """GET via priority queue with proactive sleep and 429 retry."""
        queue = get_wom_queue()
        resp: httpx.Response | None = None
        for attempt in range(3):
            resp = await queue.submit(
                lambda p=path, pa=params: self.get(p, params=pa), self._priority
            )
            if resp.status_code != 429:
                return resp
            retry_after = float(resp.headers.get("retry-after", "5"))
            logger.warning(
                "wom: 429 on {} (attempt {}) - sleeping {:.1f}s",
                path,
                attempt + 1,
                retry_after,
            )
            await asyncio.sleep(retry_after)
        return resp  # type: ignore[return-value]

    async def _write_with_rate_limit(
        self, method: str, path: str, *, json: dict | None = None
    ) -> httpx.Response:
        """POST/PUT/DELETE via priority queue with proactive sleep and 429 retry."""
        queue = get_wom_queue()
        resp: httpx.Response | None = None
        for attempt in range(3):
            if method == "post":

                async def _coro(p: str = path, j: dict | None = json) -> httpx.Response:
                    return await self.post(p, json=j)
            elif method == "put":

                async def _coro(p: str = path, j: dict | None = json) -> httpx.Response:  # type: ignore[misc]
                    return await self.put(p, json=j)
            else:

                async def _coro(p: str = path, j: dict | None = json) -> httpx.Response:  # type: ignore[misc]
                    return await self.delete(p, json=j)

            resp = await queue.submit(_coro, self._priority)
            if resp.status_code != 429:
                return resp
            retry_after = float(resp.headers.get("retry-after", "5"))
            logger.warning(
                "wom: 429 on {} {} (attempt {}) - sleeping {:.1f}s",
                method.upper(),
                path,
                attempt + 1,
                retry_after,
            )
            await asyncio.sleep(retry_after)
        return resp  # type: ignore[return-value]
