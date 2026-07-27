"""Auth helpers - JWT issuance and Discord role fetching."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import httpx
from jose import jwt
from loguru import logger

from app.services.outbound_metrics import _collector as _outbound_collector

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI", "http://localhost:8000/auth/callback"
)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_SERVER_TOKEN", "")
GUILD_ID = os.getenv("GUILD_ID", "")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")[0].strip()

_ALGORITHM = "HS256"
_DISCORD_API = "https://discord.com/api"
ROLES_REFRESH_TTL = timedelta(seconds=60)


def issue_jwt(discord_user_id: str, username: str, avatar: str | None) -> str:
    """Issue a 30-day JWT with stable identity fields only."""
    payload = {
        "sub": discord_user_id,
        "username": username,
        "avatar": avatar,
        "exp": datetime.now(UTC) + timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=_ALGORITHM)


async def fetch_discord_roles(discord_user_id: int) -> list[str]:
    """Return the member's Discord role IDs via the bot token. Returns [] on failure."""
    if not DISCORD_BOT_TOKEN:
        logger.warning(
            "discord_roles: DISCORD_SERVER_TOKEN not set - skipping role fetch"
        )
        return []
    if not GUILD_ID:
        logger.warning("discord_roles: GUILD_ID not set - skipping role fetch")
        return []

    bot_headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            t0 = time.monotonic()
            roles_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/roles", headers=bot_headers
            )
            _outbound_collector.record(
                "discord.com",
                "GET",
                f"/guilds/{GUILD_ID}/roles",
                roles_resp.status_code,
                (time.monotonic() - t0) * 1000,
            )
            if roles_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{}/roles failed ({}) - body: {}",
                    GUILD_ID,
                    roles_resp.status_code,
                    roles_resp.text,
                )
                return []
            role_map: dict[str, str] = {r["id"]: r["name"] for r in roles_resp.json()}

            t0 = time.monotonic()
            member_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/members/{discord_user_id}",
                headers=bot_headers,
            )
            _outbound_collector.record(
                "discord.com",
                "GET",
                f"/guilds/{GUILD_ID}/members/<id>",
                member_resp.status_code,
                (time.monotonic() - t0) * 1000,
            )
            if member_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{}/members/{} failed ({}) - body: {}",
                    GUILD_ID,
                    discord_user_id,
                    member_resp.status_code,
                    member_resp.text,
                )
                return []

            member_data = member_resp.json()
            role_ids = [rid for rid in member_data.get("roles", []) if rid in role_map]
            logger.info(
                "discord_roles: user {} has role IDs {} (names: {})",
                discord_user_id,
                role_ids,
                [role_map[rid] for rid in role_ids],
            )

            t0 = time.monotonic()
            guild_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}", headers=bot_headers
            )
            _outbound_collector.record(
                "discord.com",
                "GET",
                f"/guilds/{GUILD_ID}",
                guild_resp.status_code,
                (time.monotonic() - t0) * 1000,
            )
            if guild_resp.status_code == 200 and guild_resp.json().get(
                "owner_id"
            ) == str(discord_user_id):
                logger.info(
                    "discord_roles: user {} is guild owner - injecting Co-owner role ID",
                    discord_user_id,
                )
                co_owner_id = next(
                    (rid for rid, name in role_map.items() if name == "Co-owner"), None
                )
                if co_owner_id and co_owner_id not in role_ids:
                    role_ids.append(co_owner_id)
                elif not co_owner_id and "__owner__" not in role_ids:
                    role_ids.append("__owner__")

            return role_ids
    except Exception as exc:
        logger.warning("discord_roles: unexpected error: {}", exc)
        return []
