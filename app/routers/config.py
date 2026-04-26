"""Config router — server-wide configuration managed via the web panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import (
    get_admin_bypass_roles,
    require_page_permission,
)
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/config", tags=["config"])

_GLOBAL_GUILD_ID = 0
_RANK_MAPPINGS_KEY = "clan_rank_mappings"
_PAGE_PERMISSIONS_KEY = "page_permissions"
_ADMIN_BYPASS_KEY = "admin_bypass_roles"


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


# ── Rank mappings ─────────────────────────────────────────────────────────────


class RankMapping(BaseModel):
    clan_rank: str
    discord_role_id: str  # Discord snowflake ID (stable against renames)
    label: str  # Human-readable display name (e.g. "Foundry Mentors")
    order: int = 0  # Display order for privilege hierarchy


class RankMappingsBody(BaseModel):
    mappings: list[RankMapping]


@router.get(
    "/rank-mappings",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "read"))],
)
async def get_rank_mappings(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return current clan-rank -> Discord-role mappings."""
    data = await _get_config_value(_RANK_MAPPINGS_KEY, session)
    return {"mappings": data.get("mappings", [])}


@router.put(
    "/rank-mappings",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "edit"))],
)
async def set_rank_mappings(
    body: RankMappingsBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update clan-rank -> Discord-role mappings."""
    mappings = [
        m.model_dump()
        for m in body.mappings
        if m.clan_rank.strip() and m.discord_role_id.strip()
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
    """Return page permission config. Accessible to all authenticated users."""
    data = await _get_config_value(_PAGE_PERMISSIONS_KEY, session)
    bypass_roles = await get_admin_bypass_roles(session)
    return {
        "pages": data.get("pages", {}),
        "admin_bypass_roles": bypass_roles,
    }


@router.put(
    "/page-permissions",
    dependencies=[Depends(require_page_permission("staff.permissions", "edit"))],
)
async def set_page_permissions(
    body: PagePermissionsBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update page permission config."""
    pages = {k: v.model_dump() for k, v in body.pages.items()}
    await _set_config_value(_PAGE_PERMISSIONS_KEY, {"pages": pages}, session)
    return {"pages": pages}


# ── Admin bypass roles ────────────────────────────────────────────────────────


class AdminBypassBody(BaseModel):
    roles: list[str]


@router.get("/admin-bypass-roles")
async def get_admin_bypass_roles_endpoint(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the admin bypass role IDs. Accessible to all authenticated users."""
    roles = await get_admin_bypass_roles(session)
    return {"roles": roles}


@router.put("/admin-bypass-roles")
async def set_admin_bypass_roles(
    body: AdminBypassBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update admin bypass roles. Requires caller to be in current bypass list."""
    uid = int(current_user["sub"])
    caller_roles = await get_effective_roles(uid, session)
    bypass_roles = await get_admin_bypass_roles(session)
    if not any(r in bypass_roles for r in caller_roles):
        # Also accept label-based bypass for transition
        from app.services.page_permissions import _DEFAULT_BYPASS_LABELS

        cfg_result = await session.execute(
            select(Config.value).where(
                Config.guild_id == 0, Config.key == "clan_rank_mappings"
            )
        )
        cfg = cfg_result.scalar_one_or_none() or {}
        mappings = cfg.get("mappings", [])
        role_labels = {
            m["discord_role_id"]: m.get("label", "")
            for m in mappings
            if "discord_role_id" in m
        }
        caller_labels = {role_labels.get(r, r) for r in caller_roles}
        if not caller_labels & set(_DEFAULT_BYPASS_LABELS):
            from fastapi import HTTPException

            raise HTTPException(403, "Requires admin bypass role.")
    await _set_config_value(_ADMIN_BYPASS_KEY, {"roles": body.roles}, session)
    return {"roles": body.roles}
