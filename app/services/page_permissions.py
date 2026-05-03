"""Page-level permission service - DB-driven permission checks."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config
from app.dependencies import get_current_user, get_session
from app.services.rank_mappings import get_effective_roles

_GLOBAL_GUILD_ID = 0
_PAGE_PERMISSIONS_KEY = "page_permissions"
_ADMIN_BYPASS_KEY = "admin_bypass_roles"
_RANK_MAPPINGS_KEY = "clan_rank_mappings"

# Labels used as fallback when no DB bypass config exists
_DEFAULT_BYPASS_LABELS = ["Senior Moderator", "Deputy Owner", "Co-owner"]


async def _get_page_perms_config(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _PAGE_PERMISSIONS_KEY,
        )
    )
    data = result.scalar_one_or_none() or {}
    return data.get("pages", {})


async def _get_rank_mappings(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _RANK_MAPPINGS_KEY,
        )
    )
    cfg = result.scalar_one_or_none() or {}
    return cfg.get("mappings", [])


async def get_admin_bypass_roles(session: AsyncSession) -> list[str]:
    """Return admin bypass role IDs from DB, falling back to rank-mapping label lookups."""
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _ADMIN_BYPASS_KEY,
        )
    )
    stored = result.scalar_one_or_none()
    if stored is not None:
        roles = stored.get("roles")
        if isinstance(roles, list):
            return roles

    # Fallback: resolve default labels to role IDs from rank-mappings
    mappings = await _get_rank_mappings(session)
    return [
        m["discord_role_id"]
        for m in mappings
        if m.get("label") in _DEFAULT_BYPASS_LABELS and "discord_role_id" in m
    ]


async def check_page_permission(
    page_id: str,
    action: str,
    roles: list[str],
    session: AsyncSession,
) -> bool:
    """Return True if roles grant action on page_id.

    Rules (mirrors frontend checkPermission):
    - "read" with empty allowed list → True (open to all authenticated users)
    - non-read + role in bypass list → True
    - non-read + empty allowed → False
    - role in allowed list → True

    Hybrid matching: compares role IDs directly, then falls back to label-based
    matching for backwards compatibility with configs that still use role names.
    """
    bypass_roles = await get_admin_bypass_roles(session)

    # Bypass roles override ALL actions - bypass users can never be locked out.
    if bypass_roles and any(r in bypass_roles for r in roles):
        return True

    pages = await _get_page_perms_config(session)
    config = pages.get(page_id, {})
    allowed: list[str] = config.get(action, [])

    if action == "read" and not allowed:
        return True

    if not allowed:
        return False

    # Direct match (IDs or names)
    if any(r in allowed for r in roles):
        return True

    # Label-based fallback: resolve role IDs to labels and re-check.
    # Handles configs saved before role IDs were used as values.
    mappings = await _get_rank_mappings(session)
    role_labels = {
        m["discord_role_id"]: m.get("label", "")
        for m in mappings
        if "discord_role_id" in m
    }
    role_names = {role_labels.get(r, r) for r in roles}
    if role_names & set(allowed):
        return True

    return False


def require_page_permission(page_id: str, action: str):
    """FastAPI dependency factory - raises 403 if the caller lacks permission."""

    async def _dep(
        current_user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        uid = int(current_user["sub"])
        roles = await get_effective_roles(uid, session)
        if not await check_page_permission(page_id, action, roles, session):
            raise HTTPException(403, f"Requires permission: {page_id}/{action}")

    return _dep
