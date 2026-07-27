"""OSRS Wiki prices API handler."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.http.base import BaseRequestHandler


class OsrsWikiHandler(BaseRequestHandler):
    base_url = "https://prices.runescape.wiki/api/v1/osrs"
    default_headers: ClassVar[dict[str, str]] = {
        "User-Agent": "The Foundry Project - clan event tracker"
    }
    default_timeout = 5.0

    async def get_latest_prices(self, ids: list[int]) -> dict[str, Any]:
        """GET /latest?id=id1,id2,... Returns raw data dict keyed by item id string."""
        resp = await self.get("/latest", params={"id": ",".join(str(i) for i in ids)})
        resp.raise_for_status()
        return resp.json().get("data", {})


class OsrsWikiContentHandler(BaseRequestHandler):
    base_url = "https://oldschool.runescape.wiki"
    default_headers: ClassVar[dict[str, str]] = {
        "User-Agent": "The Foundry Project - clan event tracker"
    }
    default_timeout = 15.0

    async def get_page_wikitext(self, page: str) -> str:
        """Return the raw wikitext of a wiki page, or empty string on failure."""
        resp = await self.get(
            "/api.php",
            params={
                "action": "parse",
                "page": page,
                "prop": "wikitext",
                "format": "json",
                "redirects": "1",
            },
        )
        if not resp.is_success:
            return ""
        data = resp.json()
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
