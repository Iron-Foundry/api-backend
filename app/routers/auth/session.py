from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.rank_mappings import get_effective_roles
from ._helpers import ROLES_REFRESH_TTL, fetch_discord_roles, issue_jwt

router = APIRouter()


class ApiKeyRequest(BaseModel):
    api_key: str


@router.post("/token")
async def token(
    body: ApiKeyRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Exchange a web API key for a JWT."""
    result = await session.execute(
        select(User).where(User.api_key == body.api_key, User.key_is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid key")
    issued = issue_jwt(
        discord_user_id=str(user.discord_user_id),
        username=user.discord_username,
        avatar=None,
    )
    return {"token": issued}


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return authenticated user profile. Discord roles are auto-refreshed if stale."""
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

    stale = (
        row is None
        or row.roles_fetched_at is None
        or datetime.now(timezone.utc) - row.roles_fetched_at > ROLES_REFRESH_TTL
    )
    if stale:
        fresh_roles = await fetch_discord_roles(discord_user_id)
        now = datetime.now(timezone.utc)
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(discord_roles=fresh_roles, roles_fetched_at=now)
        )
        await session.commit()
        discord_roles = fresh_roles

    effective_roles = await get_effective_roles(discord_user_id, session)

    cfg_result = await session.execute(
        select(Config.value).where(
            Config.guild_id == 0, Config.key == "clan_rank_mappings"
        )
    )
    cfg = cfg_result.scalar_one_or_none() or {}
    role_labels: dict[str, str] = {
        m["discord_role_id"]: m.get("label", m["discord_role_id"])
        for m in cfg.get("mappings", [])
        if "discord_role_id" in m
    }

    alts_count: int = (
        await session.execute(
            select(func.count())
            .select_from(UserAccount)
            .where(
                UserAccount.discord_user_id == discord_user_id,
                UserAccount.is_primary.is_(False),
            )
        )
    ).scalar_one() or 0

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
