from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import (
    _DISCORD_ROLES_KEY,
    get_config_value,
    get_guild_config_value,
    set_config_value,
    set_guild_config_value,
)

router = APIRouter()


class DiscordRolesConfig(BaseModel):
    staff_role_id: str = ""
    senior_staff_role_id: str = ""
    owner_role_id: str = ""
    mentor_role_id: str = ""


class ActionLogFeatureConfig(BaseModel):
    forum_channel_id: str = ""
    enabled: bool = True


class BroadcastFeatureConfig(BaseModel):
    role_id: str = ""


class JoinRolesFeatureConfig(BaseModel):
    role_ids: list[str] = []


@router.get(
    "/discord-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_discord_roles_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = await get_config_value(_DISCORD_ROLES_KEY, session)
    return {
        "staff_role_id": data.get("staff_role_id") or os.getenv("STAFF_ROLE_ID", ""),
        "senior_staff_role_id": data.get("senior_staff_role_id")
        or os.getenv("SENIOR_STAFF_ROLE_ID", ""),
        "owner_role_id": data.get("owner_role_id") or os.getenv("OWNER_ROLE_ID", ""),
        "mentor_role_id": data.get("mentor_role_id") or os.getenv("MENTOR_ROLE_ID", ""),
    }


@router.put(
    "/discord-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_discord_roles_config(
    body: DiscordRolesConfig, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    value = body.model_dump()
    await set_config_value(_DISCORD_ROLES_KEY, value, session)
    return value


@router.get(
    "/discord-feature/action-log",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_action_log_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = await get_guild_config_value("action_log", session)
    return {
        "forum_channel_id": str(data.get("forum_channel_id", "") or ""),
        "enabled": data.get("enabled", True),
    }


@router.put(
    "/discord-feature/action-log",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_action_log_config(
    body: ActionLogFeatureConfig, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    existing = await get_guild_config_value("action_log", session)
    existing.update(
        {"forum_channel_id": body.forum_channel_id, "enabled": body.enabled}
    )
    await set_guild_config_value("action_log", existing, session)
    return {"forum_channel_id": body.forum_channel_id, "enabled": body.enabled}


@router.get(
    "/discord-feature/broadcast",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_broadcast_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = await get_guild_config_value("broadcast", session)
    return {"role_id": str(data.get("role_id", "") or "")}


@router.put(
    "/discord-feature/broadcast",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_broadcast_config(
    body: BroadcastFeatureConfig, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await set_guild_config_value("broadcast", {"role_id": body.role_id}, session)
    return {"role_id": body.role_id}


@router.get(
    "/discord-feature/join-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_join_roles_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = await get_guild_config_value("join_roles", session)
    return {"role_ids": [str(r) for r in data.get("role_ids", [])]}


@router.put(
    "/discord-feature/join-roles",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def set_join_roles_config(
    body: JoinRolesFeatureConfig, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await set_guild_config_value("join_roles", {"role_ids": body.role_ids}, session)
    return {"role_ids": body.role_ids}


@router.get(
    "/discord-feature/party-panel",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_party_panel_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read-only - party panel channel/message IDs are managed by the bot."""
    data = await get_guild_config_value("party_panel", session)
    return {
        "channel_id": str(data.get("channel_id", "") or ""),
        "message_id": str(data.get("message_id", "") or ""),
    }
