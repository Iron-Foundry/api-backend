"""WOM player-related API methods mixin."""

from __future__ import annotations

from typing import Any

from app.services.http.wom_base import WomHandlerBase


class WomPlayerMixin(WomHandlerBase):
    async def get_player_details(self, username: str) -> dict[str, Any]:
        resp = await self._get_with_rate_limit(f"/players/{username}")
        return resp.json() if resp.is_success else {}

    async def get_player_name_changes(self, username: str) -> list[dict[str, Any]]:
        """Fetch name change history for a single player. Returns [] on failure."""
        resp = await self._get_with_rate_limit(f"/players/{username}/names")
        return resp.json() if resp.is_success else []
