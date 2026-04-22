"""OSRS Wiki prices API handler."""

from __future__ import annotations

from typing import Any

from app.services.http.base import BaseRequestHandler


class OsrsWikiHandler(BaseRequestHandler):
    base_url = "https://prices.runescape.wiki/api/v1/osrs"
    default_headers: dict[str, str] = {  # type: ignore[assignment]
        "User-Agent": "The Foundry Project - clan event tracker"
    }
    default_timeout = 5.0

    async def get_latest_prices(self, ids: list[int]) -> dict[str, Any]:
        """GET /latest?id=id1,id2,... Returns raw data dict keyed by item id string."""
        resp = await self.get("/latest", params={"id": ",".join(str(i) for i in ids)})
        resp.raise_for_status()
        return resp.json().get("data", {})
