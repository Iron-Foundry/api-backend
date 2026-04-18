"""Config router — server-wide configuration managed via the web panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config
from app.dependencies import get_current_user, get_session
from app.routers.surveys import _get_roles, _has_min_rank

router = APIRouter(prefix="/config", tags=["config"])

_GLOBAL_GUILD_ID = 0


async def _get_config_value(key: str, session: AsyncSession) -> dict:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == key,
        )
    )
    return result.scalar_one_or_none() or {}


async def _set_config_value(key: str, value: dict, session: AsyncSession) -> None:
    stmt = (
        pg_insert(Config)
        .values(guild_id=_GLOBAL_GUILD_ID, key=key, value=value)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"],
            set_={"value": value},
        )
    )
    await session.execute(stmt)
    await session.commit()


# ── Rank mappings ─────────────────────────────────────────────────────────────

_RANK_MAPPINGS_KEY = "clan_rank_mappings"


class RankMapping(BaseModel):
    clan_rank: str
    discord_role: str


class RankMappingsBody(BaseModel):
    mappings: list[RankMapping]


@router.get("/rank-mappings")
async def get_rank_mappings(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return current clan-rank → Discord-role mappings. Requires Mentor or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")

    data = await _get_config_value(_RANK_MAPPINGS_KEY, session)
    return {"mappings": data.get("mappings", [])}


@router.put("/rank-mappings")
async def set_rank_mappings(
    body: RankMappingsBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update clan-rank → Discord-role mappings. Requires Senior Moderator or higher."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(status_code=403, detail="Requires Senior Moderator or higher.")

    mappings = [m.model_dump() for m in body.mappings if m.clan_rank.strip() and m.discord_role.strip()]
    await _set_config_value(_RANK_MAPPINGS_KEY, {"mappings": mappings}, session)
    return {"mappings": mappings}
