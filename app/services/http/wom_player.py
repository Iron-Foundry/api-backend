"""WOM player-related API methods mixin."""

from __future__ import annotations


class WomPlayerMixin:
    async def get_player_details(self, username: str) -> dict:
        resp = await self._get_with_rate_limit(f"/players/{username}")  # type: ignore[attr-defined]
        return resp.json() if resp.is_success else {}

    async def get_player_name_changes(self, username: str) -> list[dict]:
        """Fetch name change history for a single player. Returns [] on failure."""
        resp = await self._get_with_rate_limit(f"/players/{username}/names")  # type: ignore[attr-defined]
        return resp.json() if resp.is_success else []
