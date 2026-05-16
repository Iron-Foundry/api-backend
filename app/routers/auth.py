"""Authentication router - Discord OAuth2 and API-key login."""

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
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_session
from app.db.models import Config, User, UserAccount
from app.services.rank_mappings import get_effective_roles
from app.services.rsn_cascade import get_user_ticket_ids

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

router = APIRouter(prefix="/auth", tags=["auth"])


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
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=_ALGORITHM)


async def _fetch_discord_roles(discord_user_id: int) -> list[str]:
    """Return the member's Discord role IDs using the bot token.

    Stores stable snowflake IDs (not names) so that Discord role renames
    do not break permission checks. Returns an empty list on any failure.
    """
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
            roles_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/roles",
                headers=bot_headers,
            )
            if roles_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{}/roles failed ({}) - body: {}",
                    GUILD_ID,
                    roles_resp.status_code,
                    roles_resp.text,
                )
                return []
            # id → name map (for logging and owner injection)
            role_map: dict[str, str] = {r["id"]: r["name"] for r in roles_resp.json()}
            logger.debug("discord_roles: guild has {} roles", len(role_map))

            member_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}/members/{discord_user_id}",
                headers=bot_headers,
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
            member_role_ids: list[str] = member_data.get("roles", [])
            # Store IDs (filtered to known guild roles)
            role_ids = [rid for rid in member_role_ids if rid in role_map]
            logger.info(
                "discord_roles: user {} has role IDs {} (names: {})",
                discord_user_id,
                role_ids,
                [role_map[rid] for rid in role_ids],
            )

            guild_resp = await client.get(
                f"{_DISCORD_API}/guilds/{GUILD_ID}", headers=bot_headers
            )
            if guild_resp.status_code != 200:
                logger.warning(
                    "discord_roles: GET /guilds/{} failed ({}) - owner check skipped",
                    GUILD_ID,
                    guild_resp.status_code,
                )
            elif guild_resp.json().get("owner_id") == str(discord_user_id):
                logger.info(
                    "discord_roles: user {} is guild owner - injecting Co-owner role ID",
                    discord_user_id,
                )
                # Inject Co-owner role ID if it exists in the guild
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
    session: AsyncSession = Depends(get_session),
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

    stmt = (
        pg_insert(User)
        .values(
            discord_user_id=discord_user_id,
            discord_username=me.get("username", ""),
            discord_roles=discord_roles,
            roles_fetched_at=now,
            guild_id=int(GUILD_ID) if GUILD_ID else 0,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["discord_user_id"],
            set_={
                "discord_username": me.get("username", ""),
                "discord_roles": discord_roles,
                "roles_fetched_at": now,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)

    ticket_ids = await get_user_ticket_ids(session, discord_user_id)
    if ticket_ids:
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(ticket_ids=ticket_ids)
        )
        logger.debug(
            "auth/callback: synced {} ticket(s) for user {}",
            len(ticket_ids),
            discord_user_id,
        )

    await session.commit()

    token = _issue_jwt(
        discord_user_id=str(discord_user_id),
        username=me.get("username", ""),
        avatar=me.get("avatar"),
    )
    logger.info("auth/callback: issued JWT for user {}", discord_user_id)
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={token}")


class ApiKeyRequest(BaseModel):
    api_key: str


@router.post("/token")
async def token(
    body: ApiKeyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Exchange a web API key for a JWT."""
    result = await session.execute(
        select(User).where(
            User.api_key == body.api_key,
            User.key_is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid key")

    issued = _issue_jwt(
        discord_user_id=str(user.discord_user_id),
        username=user.discord_username,
        avatar=None,
    )
    logger.info("auth/token: issued JWT for user {}", user.discord_user_id)
    return {"token": issued}


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the authenticated user's profile, read fresh from the database.

    Discord roles are auto-refreshed if stale (60-second TTL) so members
    do not need to log out to pick up Discord role changes.
    """
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(
            User.rsn,
            User.clan_rank,
            User.discord_roles,
            User.stats_opt_out,
            User.hide_presence_notifications,
            User.roles_fetched_at,
            User.referral_source,
        ).where(User.discord_user_id == discord_user_id)
    )
    row = result.one_or_none()
    discord_roles: list[str] = (row.discord_roles if row else None) or []

    # Auto-refresh roles if stale
    stale = (
        row is None
        or row.roles_fetched_at is None
        or datetime.now(timezone.utc) - row.roles_fetched_at > ROLES_REFRESH_TTL
    )
    if stale:
        fresh_roles = await _fetch_discord_roles(discord_user_id)
        now = datetime.now(timezone.utc)
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(discord_roles=fresh_roles, roles_fetched_at=now)
        )
        await session.commit()
        discord_roles = fresh_roles

    effective_roles = await get_effective_roles(discord_user_id, session)

    # Build role_labels map from rank-mappings config
    cfg_result = await session.execute(
        select(Config.value).where(
            Config.guild_id == 0, Config.key == "clan_rank_mappings"
        )
    )
    cfg = cfg_result.scalar_one_or_none() or {}
    mappings: list[dict] = cfg.get("mappings", [])
    role_labels: dict[str, str] = {
        m["discord_role_id"]: m.get("label", m["discord_role_id"])
        for m in mappings
        if "discord_role_id" in m
    }

    alts_result = await session.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(
            UserAccount.discord_user_id == discord_user_id,
            UserAccount.is_primary == False,  # noqa: E712
        )
    )
    alts_count: int = alts_result.scalar_one() or 0

    return {
        "discord_user_id": current_user["sub"],
        "username": current_user.get("username"),
        "avatar": current_user.get("avatar"),
        "rsn": row.rsn if row else None,
        "alts_count": alts_count,
        "clan_rank": row.clan_rank if row else None,
        "discord_roles": discord_roles,
        "effective_roles": effective_roles,
        "role_labels": role_labels,
        "stats_opt_out": row.stats_opt_out if row else False,
        "hide_presence_notifications": row.hide_presence_notifications
        if row
        else False,
        "referral_source": row.referral_source if row else None,
    }
