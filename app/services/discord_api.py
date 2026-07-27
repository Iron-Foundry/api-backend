"""Discord REST API client for guild introspection."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.http.base import BaseRequestHandler

_DISCORD_BASE = "https://discord.com/api/v10"

# Channel type constants from Discord API
CHANNEL_TYPE_TEXT = 0
CHANNEL_TYPE_VOICE = 2
CHANNEL_TYPE_CATEGORY = 4
CHANNEL_TYPE_ANNOUNCEMENT = 5
CHANNEL_TYPE_STAGE = 13
CHANNEL_TYPE_FORUM = 15


class DiscordApiService(BaseRequestHandler):
    base_url: ClassVar[str] = _DISCORD_BASE
    default_timeout: ClassVar[float] = 10.0

    def __init__(self, token: str) -> None:
        super().__init__()
        self._auth = {"Authorization": f"Bot {token}"}

    async def get_channels(self, guild_id: str) -> list[dict[str, Any]]:
        """Return all channels for a guild, sorted by position."""
        resp = await self.get(f"/guilds/{guild_id}/channels", extra_headers=self._auth)
        resp.raise_for_status()
        return resp.json()

    async def get_roles(self, guild_id: str) -> list[dict[str, Any]]:
        """Return all roles for a guild."""
        resp = await self.get(f"/guilds/{guild_id}/roles", extra_headers=self._auth)
        resp.raise_for_status()
        return resp.json()


def group_channels(channels: list[dict[str, Any]]) -> dict[str, Any]:
    """Group a flat channel list into categories with nested channels."""
    categories: dict[str, dict[str, Any]] = {}
    uncategorized: list[dict[str, Any]] = []

    channel_fields = ("id", "name", "type")

    for ch in sorted(channels, key=lambda c: c.get("position", 0)):
        if ch.get("type") == CHANNEL_TYPE_CATEGORY:
            categories[str(ch["id"])] = {
                "id": str(ch["id"]),
                "name": ch["name"],
                "position": ch.get("position", 0),
                "channels": [],
            }

    for ch in sorted(channels, key=lambda c: c.get("position", 0)):
        if ch.get("type") == CHANNEL_TYPE_CATEGORY:
            continue
        slim = {
            k: (str(ch[k]) if k == "id" else ch[k]) for k in channel_fields if k in ch
        }
        parent = str(ch.get("parent_id", "")) if ch.get("parent_id") else None
        if parent and parent in categories:
            categories[parent]["channels"].append(slim)
        else:
            uncategorized.append(slim)

    sorted_cats = sorted(categories.values(), key=lambda c: c["position"])
    for cat in sorted_cats:
        del cat["position"]

    return {
        "categories": sorted_cats,
        "uncategorized": uncategorized,
    }
