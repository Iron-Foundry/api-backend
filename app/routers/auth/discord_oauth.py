from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.services.rsn_cascade import get_user_ticket_ids
from ._helpers import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    FRONTEND_URL,
    GUILD_ID,
    JWT_SECRET,
    _ALGORITHM,
    _DISCORD_API,
    fetch_discord_roles,
    issue_jwt,
)

router = APIRouter()


@router.get("/login")
async def login() -> RedirectResponse:
    state = jwt.encode(
        {
            "nonce": uuid4().hex,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
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
    discord_roles = await fetch_discord_roles(discord_user_id)
    now = datetime.now(timezone.utc)

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
