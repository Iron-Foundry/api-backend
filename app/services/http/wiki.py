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

    async def get_page_thumbnails(
        self, pages: list[str], size: int = 64
    ) -> dict[str, str]:
        """Map each requested page title to its lead image URL, skipping the ones without.

        One `action=query` call for the whole batch (MediaWiki accepts 50 titles).
        Titles the wiki normalises or redirects are mapped back to what was asked
        for, so the caller can look up by the name it passed in.
        """
        if not pages:
            return {}
        resp = await self.get(
            "/api.php",
            params={
                "action": "query",
                "titles": "|".join(pages),
                "prop": "pageimages",
                "pithumbsize": size,
                "format": "json",
                "redirects": "1",
            },
        )
        if not resp.is_success:
            return {}
        data = resp.json().get("query", {})
        by_title = {
            page["title"]: page["thumbnail"]["source"]
            for page in data.get("pages", {}).values()
            if page.get("thumbnail", {}).get("source")
        }
        for hop in ("normalized", "redirects"):
            for entry in data.get(hop, []):
                resolved = by_title.get(entry["to"])
                if resolved:
                    by_title[entry["from"]] = resolved
        return {page: by_title[page] for page in pages if page in by_title}
