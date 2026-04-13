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
    rsn: str | None,
    clan_rank: str | None,
) -> str:
    payload = {
        "sub": discord_user_id,
        "username": username,
        "avatar": avatar,
        "rsn": rsn,
        "clan_rank": clan_rank,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=_ALGORITHM)


async def _lookup_user(db: AsyncDatabase, discord_user_id: int) -> dict:
    """Return rsn and clan_rank from the users collection, or empty strings."""
    doc = await db["users"].find_one(
        {"discord_user_id": discord_user_id}, {"rsn": 1, "clan_rank": 1}
    )
    if doc:
        return {"rsn": doc.get("rsn"), "clan_rank": doc.get("clan_rank")}
    return {"rsn": None, "clan_rank": None}


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
    profile = await _lookup_user(db, discord_user_id)
    token = _issue_jwt(
        discord_user_id=str(discord_user_id),
        username=me.get("username", ""),
        avatar=me.get("avatar"),
        rsn=profile["rsn"],
        clan_rank=profile["clan_rank"],
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
    profile = await _lookup_user(db, discord_user_id)
    issued = _issue_jwt(
        discord_user_id=str(discord_user_id),
        username=doc.get("discord_username", ""),
        avatar=doc.get("avatar_hash"),
        rsn=profile["rsn"],
        clan_rank=profile["clan_rank"],
    )
    logger.info("auth/token: issued JWT for user {}", discord_user_id)
    return {"token": issued}


# ── Current-user endpoint ──────────────────────────────────────────────────


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    """Return the authenticated user's profile."""
    return {
        "discord_user_id": current_user["sub"],
        "username": current_user.get("username"),
        "avatar": current_user.get("avatar"),
        "rsn": current_user.get("rsn"),
        "clan_rank": current_user.get("clan_rank"),
    }
