"""Config router - server-wide configuration managed via the web panel."""

from __future__ import annotations

import os

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
_DISCORD_GUILD_ID = int(os.getenv("GUILD_ID", "0"))
_RANK_MAPPINGS_KEY = "clan_rank_mappings"
_PAGE_PERMISSIONS_KEY = "page_permissions"
_ADMIN_BYPASS_KEY = "admin_bypass_roles"
_PARTY_PING_ROLES_KEY = "party_ping_roles"
_RANKING_CONFIG_KEY = "ranking_config"
_DISCORD_ROLES_KEY = "discord_roles"


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


async def _get_guild_config_value(key: str, session: AsyncSession) -> dict:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _DISCORD_GUILD_ID,
            Config.key == key,
        )
    )
    return result.scalar_one_or_none() or {}


async def _set_guild_config_value(key: str, value: dict, session: AsyncSession) -> None:
    stmt = (
        pg_insert(Config)
        .values(guild_id=_DISCORD_GUILD_ID, key=key, value=value)
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


# ── Party ping roles ─────────────────────────────────────────────────────────


class PartyPingRoleEntry(BaseModel):
    discord_role_id: str
    label: str


class PartyPingRolesBody(BaseModel):
    roles: list[PartyPingRoleEntry]


@router.get("/party-ping-roles")
async def get_party_ping_roles(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the list of Discord roles that party leaders can ping. Any authenticated user."""
    data = await _get_config_value(_PARTY_PING_ROLES_KEY, session)
    return {"roles": data.get("roles", [])}


@router.put(
    "/party-ping-roles",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "edit"))],
)
async def set_party_ping_roles(
    body: PartyPingRolesBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update the party ping roles list. Requires rank-mappings edit permission."""
    roles = [
        r.model_dump()
        for r in body.roles
        if r.discord_role_id.strip() and r.label.strip()
    ]
    await _set_config_value(_PARTY_PING_ROLES_KEY, {"roles": roles}, session)
    return {"roles": roles}


# ── Admin bypass roles ────────────────────────────────────────────────────────


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


# ── Ranking config ────────────────────────────────────────────────────────────


@router.get(
    "/ranking",
    dependencies=[Depends(require_page_permission("staff.ranking", "read"))],
)
async def get_ranking_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.services.ranking_service import _DEFAULT_CONFIG

    data = await _get_config_value(_RANKING_CONFIG_KEY, session)
    if not data:
        return _DEFAULT_CONFIG
    merged = dict(_DEFAULT_CONFIG)
    merged.update(data)
    return merged


@router.put(
    "/ranking",
    dependencies=[Depends(require_page_permission("staff.ranking", "edit"))],
)
async def set_ranking_config(
    body: dict,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _set_config_value(_RANKING_CONFIG_KEY, body, session)
    return body


# ── Discord roles config ──────────────────────────────────────────────────────


class DiscordRolesConfig(BaseModel):
    staff_role_id: str = ""
    senior_staff_role_id: str = ""
    owner_role_id: str = ""
    mentor_role_id: str = ""


@router.get(
    "/discord-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_discord_roles_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return configured staff Discord role IDs, falling back to env vars."""
    data = await _get_config_value(_DISCORD_ROLES_KEY, session)
    return {
        "staff_role_id": data.get("staff_role_id") or os.getenv("STAFF_ROLE_ID", ""),
        "senior_staff_role_id": data.get("senior_staff_role_id") or os.getenv("SENIOR_STAFF_ROLE_ID", ""),
        "owner_role_id": data.get("owner_role_id") or os.getenv("OWNER_ROLE_ID", ""),
        "mentor_role_id": data.get("mentor_role_id") or os.getenv("MENTOR_ROLE_ID", ""),
    }


@router.put(
    "/discord-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_discord_roles_config(
    body: DiscordRolesConfig,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update staff Discord role IDs."""
    value = body.model_dump()
    await _set_config_value(_DISCORD_ROLES_KEY, value, session)
    return value


# ── Discord feature configs ───────────────────────────────────────────────────


class ActionLogFeatureConfig(BaseModel):
    forum_channel_id: str = ""
    enabled: bool = True


class BroadcastFeatureConfig(BaseModel):
    role_id: str = ""


class JoinRolesFeatureConfig(BaseModel):
    role_ids: list[str] = []


@router.get(
    "/discord-feature/action-log",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_action_log_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await _get_guild_config_value("action_log", session)
    return {
        "forum_channel_id": str(data.get("forum_channel_id", "") or ""),
        "enabled": data.get("enabled", True),
    }


@router.put(
    "/discord-feature/action-log",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_action_log_config(
    body: ActionLogFeatureConfig,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Preserve bot-managed fields (thread_ids, etc.) by merging
    existing = await _get_guild_config_value("action_log", session)
    existing.update({"forum_channel_id": body.forum_channel_id, "enabled": body.enabled})
    await _set_guild_config_value("action_log", existing, session)
    return {"forum_channel_id": body.forum_channel_id, "enabled": body.enabled}


@router.get(
    "/discord-feature/broadcast",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_broadcast_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await _get_guild_config_value("broadcast", session)
    return {"role_id": str(data.get("role_id", "") or "")}


@router.put(
    "/discord-feature/broadcast",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_broadcast_config(
    body: BroadcastFeatureConfig,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _set_guild_config_value("broadcast", {"role_id": body.role_id}, session)
    return {"role_id": body.role_id}


@router.get(
    "/discord-feature/join-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_join_roles_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await _get_guild_config_value("join_roles", session)
    return {"role_ids": [str(r) for r in data.get("role_ids", [])]}


@router.put(
    "/discord-feature/join-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_join_roles_config(
    body: JoinRolesFeatureConfig,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _set_guild_config_value("join_roles", {"role_ids": body.role_ids}, session)
    return {"role_ids": body.role_ids}


@router.get(
    "/discord-feature/party-panel",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_party_panel_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Read-only - party panel channel/message IDs are managed by the bot."""
    data = await _get_guild_config_value("party_panel", session)
    return {
        "channel_id": str(data.get("channel_id", "") or ""),
        "message_id": str(data.get("message_id", "") or ""),
    }
