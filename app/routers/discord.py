"""Discord router - exposes guild channel/role data for the web admin UI."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.services.discord_api import DiscordApiService, group_channels
from app.services.page_permissions import require_page_permission

router = APIRouter(prefix="/discord", tags=["discord"])

_TOKEN = os.getenv("DISCORD_TOKEN", "")
_GUILD_ID = os.getenv("GUILD_ID", "")


def _check_configured() -> None:
    if not _TOKEN or not _GUILD_ID:
        raise HTTPException(503, "DISCORD_TOKEN or GUILD_ID not configured")


@router.get(
    "/channels",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_discord_channels() -> dict:
    """Return guild channels grouped by category."""
    _check_configured()
    try:
        svc = DiscordApiService(_TOKEN)
        channels = await svc.get_channels(_GUILD_ID)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Discord API error: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Discord API unreachable: {exc}") from exc
    return group_channels(channels)


@router.get(
    "/emojis",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_discord_emojis() -> dict:
    """Return guild custom emojis."""
    _check_configured()
    try:
        svc = DiscordApiService(_TOKEN)
        resp = await svc.get(f"/guilds/{_GUILD_ID}/emojis", extra_headers={"Authorization": f"Bot {_TOKEN}"})
        resp.raise_for_status()
        emojis = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Discord API error: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Discord API unreachable: {exc}") from exc

    return {
        "emojis": [
            {
                "id": str(e["id"]),
                "name": e["name"],
                "animated": e.get("animated", False),
            }
            for e in emojis
            if e.get("available", True)
        ]
    }


@router.get(
    "/roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_discord_roles() -> dict:
    """Return guild roles sorted by position descending, excluding @everyone."""
    _check_configured()
    try:
        svc = DiscordApiService(_TOKEN)
        roles = await svc.get_roles(_GUILD_ID)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Discord API error: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Discord API unreachable: {exc}") from exc

    filtered = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "color": r.get("color", 0),
            "position": r.get("position", 0),
        }
        for r in roles
        if str(r["id"]) != _GUILD_ID
    ]
    filtered.sort(key=lambda r: r["position"], reverse=True)
    return {"roles": filtered}
