from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from loguru import logger
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.dependencies import get_session
from app.services.outbound_metrics import _collector as _outbound_collector
from app.services.rsn_cascade import get_user_ticket_ids

from ._helpers import (
    _ALGORITHM,
    _DISCORD_API,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    FRONTEND_URL,
    GUILD_ID,
    JWT_SECRET,
    fetch_discord_roles,
    issue_jwt,
)

router = APIRouter()


@router.get("/login")
async def login() -> RedirectResponse:
    """Redirect to Discord's OAuth2 consent screen.

    A browser redirect, not a JSON endpoint. The signed `state` parameter
    expires after five minutes.
    """
    state = jwt.encode(
        {
            "nonce": uuid4().hex,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm=_ALGORITHM,
    )
    params = f"client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds&state={state}"
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Complete the OAuth2 exchange and hand the browser a JWT.

    Verifies the caller is in the clan's guild, upserts their user record with
    their current Discord roles, then redirects to the frontend with the token
    in the query string. Failures redirect back with an `error` parameter
    rather than returning a status code.
    """
    if error or not code or not state:
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_cancelled")

    try:
        jwt.decode(state, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        logger.warning("auth/callback: invalid state JWT")
        return RedirectResponse(f"{FRONTEND_URL}?error=invalid_state")

    async with httpx.AsyncClient() as client:
        t0 = time.monotonic()
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
        _outbound_collector.record(
            "discord.com",
            "POST",
            "/oauth2/token",
            token_resp.status_code,
            (time.monotonic() - t0) * 1000,
        )
        if token_resp.status_code != 200:
            logger.warning("auth/callback: token exchange failed: {}", token_resp.text)
            return RedirectResponse(f"{FRONTEND_URL}?error=token_exchange_failed")

        access_token: str = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        t0 = time.monotonic()
        me_resp = await client.get(f"{_DISCORD_API}/users/@me", headers=headers)
        _outbound_collector.record(
            "discord.com",
            "GET",
            "/users/@me",
            me_resp.status_code,
            (time.monotonic() - t0) * 1000,
        )
        me = me_resp.json()
        t0 = time.monotonic()
        guilds_resp = await client.get(
            f"{_DISCORD_API}/users/@me/guilds", headers=headers
        )
        _outbound_collector.record(
            "discord.com",
            "GET",
            "/users/@me/guilds",
            guilds_resp.status_code,
            (time.monotonic() - t0) * 1000,
        )
        guild_ids = {g["id"] for g in guilds_resp.json()}

    if GUILD_ID and str(GUILD_ID) not in guild_ids:
        logger.info("auth/callback: user {} not in guild {}", me.get("id"), GUILD_ID)
        return RedirectResponse(f"{FRONTEND_URL}?error=not_member")

    discord_user_id = int(me["id"])
    discord_roles = await fetch_discord_roles(discord_user_id)
    now = datetime.now(UTC)

    await session.execute(
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
    token = issue_jwt(
        discord_user_id=str(discord_user_id),
        username=me.get("username", ""),
        avatar=me.get("avatar"),
    )
    logger.info("auth/callback: issued JWT for user {}", discord_user_id)
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={token}")
