from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import _DEFAULT_BYPASS_LABELS, get_admin_bypass_roles, require_page_permission
from app.services.rank_mappings import get_effective_roles

from ._helpers import (
    _ADMIN_BYPASS_KEY,
    _NOTIFICATION_CATEGORIES_KEY,
    _PAGE_PERMISSIONS_KEY,
    _RANK_MAPPINGS_KEY,
    get_config_value,
    set_config_value,
)

router = APIRouter()


class RankMapping(BaseModel):
    clan_rank: str
    discord_role_id: str
    label: str
    order: int = 0


class RankMappingsBody(BaseModel):
    mappings: list[RankMapping]


class PagePermissionEntry(BaseModel):
    read: list[str] = []
    create: list[str] = []
    edit: list[str] = []
    delete: list[str] = []


class PagePermissionsBody(BaseModel):
    pages: dict[str, PagePermissionEntry]


class AdminBypassBody(BaseModel):
    roles: list[str]


class NotificationCategoryEntry(BaseModel):
    id: str
    label: str


class NotificationCategoriesBody(BaseModel):
    categories: list[NotificationCategoryEntry]


@router.get(
    "/rank-mappings",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "read"))],
)
async def get_rank_mappings(session: AsyncSession = Depends(get_session)) -> dict:
    data = await get_config_value(_RANK_MAPPINGS_KEY, session)
    return {"mappings": data.get("mappings", [])}


@router.put(
    "/rank-mappings",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "edit"))],
)
async def set_rank_mappings(
    body: RankMappingsBody, session: AsyncSession = Depends(get_session)
) -> dict:
    mappings = [
        m.model_dump() for m in body.mappings if m.clan_rank.strip() and m.discord_role_id.strip()
    ]
    await set_config_value(_RANK_MAPPINGS_KEY, {"mappings": mappings}, session)
    return {"mappings": mappings}


@router.get("/page-permissions")
async def get_page_permissions(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_config_value(_PAGE_PERMISSIONS_KEY, session)
    bypass_roles = await get_admin_bypass_roles(session)
    return {"pages": data.get("pages", {}), "admin_bypass_roles": bypass_roles}


@router.put(
    "/page-permissions",
    dependencies=[Depends(require_page_permission("staff.permissions", "edit"))],
)
async def set_page_permissions(
    body: PagePermissionsBody, session: AsyncSession = Depends(get_session)
) -> dict:
    pages = {k: v.model_dump() for k, v in body.pages.items()}
    await set_config_value(_PAGE_PERMISSIONS_KEY, {"pages": pages}, session)
    return {"pages": pages}


@router.get("/admin-bypass-roles")
async def get_admin_bypass_roles_endpoint(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    roles = await get_admin_bypass_roles(session)
    return {"roles": roles}


@router.put("/admin-bypass-roles")
async def set_admin_bypass_roles(
    body: AdminBypassBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    uid = int(current_user["sub"])
    caller_roles = await get_effective_roles(uid, session)
    bypass_roles = await get_admin_bypass_roles(session)
    if not any(r in bypass_roles for r in caller_roles):
        cfg_result = await session.execute(
            select(Config.value).where(Config.guild_id == 0, Config.key == "clan_rank_mappings")
        )
        cfg = cfg_result.scalar_one_or_none() or {}
        role_labels = {
            m["discord_role_id"]: m.get("label", "")
            for m in cfg.get("mappings", [])
            if "discord_role_id" in m
        }
        caller_labels = {role_labels.get(r, r) for r in caller_roles}
        if not caller_labels & set(_DEFAULT_BYPASS_LABELS):
            raise HTTPException(403, "Requires admin bypass role.")
    await set_config_value(_ADMIN_BYPASS_KEY, {"roles": body.roles}, session)
    return {"roles": body.roles}


@router.get("/party-notification-categories")
async def get_notification_categories(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_config_value(_NOTIFICATION_CATEGORIES_KEY, session)
    return {"categories": data.get("categories", [])}


@router.put(
    "/party-notification-categories",
    dependencies=[Depends(require_page_permission("staff.rank-mappings", "edit"))],
)
async def set_notification_categories(
    body: NotificationCategoriesBody, session: AsyncSession = Depends(get_session)
) -> dict:
    categories = [c.model_dump() for c in body.categories if c.id.strip() and c.label.strip()]
    await set_config_value(_NOTIFICATION_CATEGORIES_KEY, {"categories": categories}, session)
    return {"categories": categories}
