"""Discord party integration - no-ops.

Party display on Discord is handled entirely by the discord-server bot panel.
The bot polls the database every 30 seconds and refreshes the panel in place.
These functions are intentionally inert so the API does not post duplicate
webhook messages alongside the panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import PartyDB as Party


async def post_party_embed(party: Party) -> str | None:  # noqa: ARG001
    return None


async def edit_party_embed(party: Party) -> None:  # noqa: ARG001
    return


async def close_party_embed(party: Party) -> None:  # noqa: ARG001
    return
