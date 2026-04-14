# DEPRECATED — MongoDB implementation. Kept for reference. Not imported in production.
"""Authentication router — Discord OAuth2 and API-key login."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from loguru import logger
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.dependencies import get_current_user, get_db

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

router = APIRouter(prefix="/auth", tags=["auth"])


# ── helpers ────────────────────────────────────────────────────────────────


def _issue_jwt(
    discord_user_id: str,
    username: str,
    avatar: str | None,
) -> str:
    """Issue a JWT containing only stable identity fields.

    Mutable profile data (rsn, clan_rank, discord_roles, stats_opt_out) is
    read fresh from the database on every /auth/me call instead of being
    embedded in the token.
    """
    payload = {
        "sub": discord_user_id,
        "username": username,
        "avatar": avatar,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=_ALGORITHM)


async def _fetch_discord_roles(discord_user_id: int) -> list[str]:
    """Return the member's Discord role names using the bot token.

    Returns an empty list if DISCORD_BOT_TOKEN or GUILD_ID is not configured,
    or if the Discord API call fails for any reason.
    """
    if not DISCORD_BOT_TOKEN:
        logger.warning("discord_roles: DISCORD_SERVER_TOKEN not set — skipping role fetch")
        return []
    if not GUILD_ID:
        logger.warning("discord_roles: GUILD_ID not set — skipping role fetch")
        return []

    bot_headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            roles_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/roles",
                headers=bot_headers,
            )
            if roles_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{}/roles failed ({}) — body: {}",
                    GUILD_ID,
                    roles_resp.status_code,
                    roles_resp.text,
                )
                return []
            role_map: dict[str, str] = {r["id"]: r["name"] for r in roles_resp.json()}
            logger.debug("discord_roles: guild has {} roles", len(role_map))

            member_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/members/{discord_user_id}",
                headers=bot_headers,
            )
            if member_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{}/members/{} failed ({}) — body: {}",
                    GUILD_ID,
                    discord_user_id,
                    member_resp.status_code,
                    member_resp.text,
                )
                return []

            member_data = member_resp.json()
            member_role_ids: list[str] = member_data.get("roles", [])
            role_names = [role_map[rid] for rid in member_role_ids if rid in role_map]
            logger.info(
                "discord_roles: user {} has role IDs {} → names {}",
                discord_user_id,
                member_role_ids,
                role_names,
            )

            # Guild owner has no explicit role — inject Co-owner.
            guild_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}", headers=bot_headers
            )
            if guild_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{} failed ({}) — owner check skipped",
                    GUILD_ID,
                    guild_resp.status_code,
                )
            elif guild_resp.json().get("owner_id") == str(discord_user_id):
                logger.info("discord_roles: user {} is guild owner — injecting Co-owner", discord_user_id)
                if "Co-owner" not in role_names:
                    role_names.append("Co-owner")

            return role_names
    except Exception as exc:
        logger.warning("discord_roles: unexpected error: {}", exc)
        return []


# ── OAuth2 endpoints ───────────────────────────────────────────────────────


@router.get("/login")
async def login() -> RedirectResponse:
    """Redirect the browser to Discord's OAuth2 consent screen."""
    state = jwt.encode(
        {
            "nonce": uuid4().hex,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm=_ALGORITHM,
    )
    params = (
        f"client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
        f"&state={state}"
    )
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncDatabase = Depends(get_db),
) -> RedirectResponse:
    """Handle the OAuth2 redirect from Discord."""
    if error or not code or not state:
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_cancelled")

    try:
        jwt.decode(state, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        logger.warning("auth/callback: invalid state JWT")
        return RedirectResponse(f"{FRONTEND_URL}?error=invalid_state")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{_DISCORD_API}/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.warning("auth/callback: token exchange failed: {}", token_resp.text)
            return RedirectResponse(f"{FRONTEND_URL}?error=token_exchange_failed")

        access_token: str = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        me_resp = await client.get(f"{_DISCORD_API}/users/@me", headers=headers)
        me = me_resp.json()

        guilds_resp = await client.get(
            f"{_DISCORD_API}/users/@me/guilds", headers=headers
        )
        guild_ids = {g["id"] for g in guilds_resp.json()}

    if GUILD_ID and str(GUILD_ID) not in guild_ids:
        logger.info("auth/callback: user {} not in guild {}", me.get("id"), GUILD_ID)
        return RedirectResponse(f"{FRONTEND_URL}?error=not_member")

    discord_user_id = int(me["id"])
    discord_roles = await _fetch_discord_roles(discord_user_id)
    now = datetime.now(timezone.utc)

    # Upsert user — create minimal doc on first login, update identity + roles always.
    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {
            "$set": {
                "discord_username": me.get("username", ""),
                "discord_roles": discord_roles,
                "updated_at": now,
            },
            "$setOnInsert": {
                "guild_id": int(GUILD_ID) if GUILD_ID else 0,
                "guild_name": "",
                "rsn": None,
                "clan_rank": None,
                "stats_opt_out": False,
                "ticket_ids": [],
                "created_at": now,
            },
        },
        upsert=True,
    )

    # Sync ticket_ids from the tickets collection (keyed by Discord user ID).
    ticket_ids: list[int] = []
    async for doc in db["tickets"].find(
        {"creator.id": discord_user_id}, {"ticket_id": 1, "_id": 0}
    ):
        if isinstance(doc.get("ticket_id"), int):
            ticket_ids.append(doc["ticket_id"])
    if ticket_ids:
        await db["users"].update_one(
            {"discord_user_id": discord_user_id},
            {"$set": {"ticket_ids": sorted(ticket_ids)}},
        )
        logger.debug(
            "auth/callback: synced {} ticket(s) for user {}", len(ticket_ids), discord_user_id
        )

    token = _issue_jwt(
        discord_user_id=str(discord_user_id),
        username=me.get("username", ""),
        avatar=me.get("avatar"),
    )
    logger.info("auth/callback: issued JWT for user {}", discord_user_id)
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={token}")


# ── API-key login ──────────────────────────────────────────────────────────


class ApiKeyRequest(BaseModel):
    api_key: str


@router.post("/token")
async def token(
    body: ApiKeyRequest,
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Exchange a web API key for a JWT."""
    doc = await db["user_keys"].find_one({"key": body.api_key, "is_active": True})
    if not doc:
        raise HTTPException(status_code=401, detail="Invalid key")

    discord_user_id = int(doc["discord_user_id"])
    issued = _issue_jwt(
        discord_user_id=str(discord_user_id),
        username=doc.get("discord_username", ""),
        avatar=doc.get("avatar_hash"),
    )
    logger.info("auth/token: issued JWT for user {}", discord_user_id)
    return {"token": issued}


# ── Current-user endpoint ──────────────────────────────────────────────────


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Return the authenticated user's profile, read fresh from the database.

    Mutable fields (rsn, clan_rank, discord_roles, stats_opt_out) are always
    fetched from MongoDB so changes are visible without re-login.
    """
    discord_user_id = int(current_user["sub"])
    doc = await db["users"].find_one(
        {"discord_user_id": discord_user_id},
        {"rsn": 1, "clan_rank": 1, "discord_roles": 1, "stats_opt_out": 1},
    )
    return {
        "discord_user_id": current_user["sub"],
        "username": current_user.get("username"),
        "avatar": current_user.get("avatar"),
        "rsn": doc.get("rsn") if doc else None,
        "clan_rank": doc.get("clan_rank") if doc else None,
        "discord_roles": doc.get("discord_roles", []) if doc else [],
        "stats_opt_out": doc.get("stats_opt_out", False) if doc else False,
    }
