"""Config router — server-wide configuration managed via the web panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config
from app.dependencies import get_current_user, get_session
from app.routers.surveys import _has_min_rank
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/config", tags=["config"])

_GLOBAL_GUILD_ID = 0
_RANK_MAPPINGS_KEY = "clan_rank_mappings"
_PAGE_PERMISSIONS_KEY = "page_permissions"


# ── Shared helpers ────────────────────────────────────────────────────────────

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


async def _require_rank(
    min_rank: str,
    current_user: dict,
    session: AsyncSession,
) -> None:
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not _has_min_rank(roles, min_rank):
        raise HTTPException(
            status_code=403, detail=f"Requires {min_rank} or higher."
        )


# ── Rank mappings ─────────────────────────────────────────────────────────────

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
    await _require_rank("Foundry Mentors", current_user, session)
    data = await _get_config_value(_RANK_MAPPINGS_KEY, session)
    return {"mappings": data.get("mappings", [])}


@router.put("/rank-mappings")
async def set_rank_mappings(
    body: RankMappingsBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update clan-rank → Discord-role mappings. Requires Senior Moderator or higher."""
    await _require_rank("Senior Moderator", current_user, session)
    mappings = [
        m.model_dump()
        for m in body.mappings
        if m.clan_rank.strip() and m.discord_role.strip()
    ]
    await _set_config_value(_RANK_MAPPINGS_KEY, {"mappings": mappings}, session)
    return {"mappings": mappings}


# ── Page permissions ──────────────────────────────────────────────────────────

class PagePermissionEntry(BaseModel):
    read: list[str] = []
    create: list[str] = []
    edit: list[str] = []
    delete: list[str] = []


class PagePermissionsBody(BaseModel):
    pages: dict[str, PagePermissionEntry]


@router.get("/page-permissions")
async def get_page_permissions(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return page permission config. Requires Mentor or higher."""
    await _require_rank("Foundry Mentors", current_user, session)
    data = await _get_config_value(_PAGE_PERMISSIONS_KEY, session)
    return {"pages": data.get("pages", {})}


@router.put("/page-permissions")
async def set_page_permissions(
    body: PagePermissionsBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update page permission config. Requires Senior Moderator or higher."""
    await _require_rank("Senior Moderator", current_user, session)
    pages = {k: v.model_dump() for k, v in body.pages.items()}
    await _set_config_value(_PAGE_PERMISSIONS_KEY, {"pages": pages}, session)
    return {"pages": pages}
