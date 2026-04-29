"""Discord webhook integration for party announcements."""

from __future__ import annotations

import os
from datetime import timezone

import httpx
from loguru import logger

from app.party_store import VIBE_COLOUR, Party

WEBHOOK_URL = os.getenv("DISCORD_PARTY_WEBHOOK_URL", "").rstrip("/")
_SITE_URL = os.getenv("FRONTEND_URL", "https://ironfoundry.cc").split(",")[0].strip().rstrip("/")
_PARTIES_URL = f"{_SITE_URL}/parties"
_CLOSED_COLOUR = 0x95A5A6


def _build_embed(party: Party) -> dict:
    is_closed = party.status == "closed"
    is_full = party.status == "full"

    if is_closed:
        title = f"{party.activity} — Closed"
        colour = _CLOSED_COLOUR
    elif is_full:
        title = f"{party.activity} — Full"
        colour = _CLOSED_COLOUR
    else:
        title = party.activity
        colour = VIBE_COLOUR.get(party.vibe, 0xF1C40F)

    leader_display = party.leader_rsn or party.leader_username
    members_display = ", ".join(m.rsn or m.username for m in party.members) or "—"

    fields: list[dict] = [
        {"name": "Leader",  "value": leader_display, "inline": True},
        {"name": "Vibe",    "value": party.vibe.capitalize(), "inline": True},
        {"name": "Spots",   "value": f"{len(party.members)} / {party.max_size}", "inline": True},
    ]
    if party.scheduled_at:
        aware = party.scheduled_at if party.scheduled_at.tzinfo else party.scheduled_at.replace(tzinfo=timezone.utc)
        fields.append({"name": "Scheduled", "value": f"<t:{int(aware.timestamp())}:R>", "inline": True})
    if not is_closed:
        fields.append({"name": "Expires", "value": f"<t:{int(party.expires_at.timestamp())}:R>", "inline": True})
    fields.append({"name": "Members", "value": members_display, "inline": False})
    if party.ping_role_ids:
        fields.append({"name": "Pinged", "value": " ".join(f"<@&{rid}>" for rid in party.ping_role_ids), "inline": False})

    return {
        "title": title,
        "url": _PARTIES_URL,
        "description": party.description or "",
        "color": colour,
        "fields": fields,
        "footer": {"text": "Iron Foundry Parties"},
        "timestamp": party.created_at.isoformat(),
    }


async def post_party_embed(party: Party) -> str | None:
    """POST a new embed to the webhook. Returns the Discord message ID."""
    if not WEBHOOK_URL:
        return None
    content = " ".join(f"<@&{rid}>" for rid in party.ping_role_ids) if party.ping_role_ids else ""
    payload: dict = {
        "embeds": [_build_embed(party)],
        "allowed_mentions": {"parse": [], "roles": list(party.ping_role_ids)},
    }
    if content:
        payload["content"] = content
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{WEBHOOK_URL}?wait=true", json=payload)
            resp.raise_for_status()
            return str(resp.json().get("id"))
    except Exception as exc:
        logger.warning("discord_party.post: {}", exc)
        return None


async def edit_party_embed(party: Party) -> None:
    """PATCH the existing embed to reflect current party state."""
    if not WEBHOOK_URL or not party.discord_message_id:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{WEBHOOK_URL}/messages/{party.discord_message_id}",
                json={"embeds": [_build_embed(party)], "allowed_mentions": {"parse": []}},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("discord_party.edit: {}", exc)


async def close_party_embed(party: Party) -> None:
    """Convenience wrapper — updates the embed to show the closed state."""
    await edit_party_embed(party)
