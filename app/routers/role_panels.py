"""Role panels router - manage Discord role selection panels via the web admin UI."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RolePanel
from app.dependencies import get_session
from app.docs import responses
from app.services.page_permissions import require_page_permission

router = APIRouter(
    prefix="/role-panels", tags=["role-panels"], responses=responses.STAFF_LOOKUP
)

_GUILD_ID = int(os.getenv("GUILD_ID", "0"))


# ── Schemas ───────────────────────────────────────────────────────────────────


class SelectableRole(BaseModel):
    role_id: str  # string snowflake for JSON safety
    label: str
    description: str = ""
    emoji: str | None = None


class RolePanelUpdate(BaseModel):
    title: str
    description: str = ""
    max_selectable: int | None = None
    roles: list[SelectableRole] = []


# ── Helpers ───────────────────────────────────────────────────────────────────


def _serialize(panel: RolePanel) -> dict[str, Any]:
    return {
        "panel_id": panel.panel_id,
        "guild_id": str(panel.guild_id),
        "channel_id": str(panel.channel_id),
        "message_id": str(panel.message_id),
        "title": panel.title,
        "description": panel.description,
        "max_selectable": panel.max_selectable,
        "roles": [
            {
                "role_id": str(r.get("role_id", "")),
                "label": r.get("label", ""),
                "description": r.get("description", ""),
                "emoji": r.get("emoji"),
            }
            for r in (panel.roles or [])
        ],
        "created_at": panel.created_at.isoformat(),
        "updated_at": panel.updated_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def list_role_panels(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all role panels for the guild."""
    result = await session.execute(
        select(RolePanel)
        .where(RolePanel.guild_id == _GUILD_ID)
        .order_by(RolePanel.created_at)
    )
    panels = result.scalars().all()
    return {"panels": [_serialize(p) for p in panels]}


@router.get(
    "/{panel_id}",
    dependencies=[Depends(require_page_permission("staff.discord-config", "read"))],
)
async def get_role_panel(
    panel_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return one self-assign role panel with its buttons and roles."""
    result = await session.execute(
        select(RolePanel).where(
            RolePanel.panel_id == panel_id, RolePanel.guild_id == _GUILD_ID
        )
    )
    panel = result.scalar_one_or_none()
    if panel is None:
        raise HTTPException(404, "Panel not found")
    return _serialize(panel)


@router.put(
    "/{panel_id}",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def update_role_panel(
    panel_id: str,
    body: RolePanelUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update panel metadata and roles list. Run /rolepanel refresh in Discord to sync the embed."""
    result = await session.execute(
        select(RolePanel).where(
            RolePanel.panel_id == panel_id, RolePanel.guild_id == _GUILD_ID
        )
    )
    panel = result.scalar_one_or_none()
    if panel is None:
        raise HTTPException(404, "Panel not found")

    panel.title = body.title
    panel.description = body.description
    panel.max_selectable = body.max_selectable
    panel.roles = [
        {
            "role_id": r.role_id,  # store as string to preserve 64-bit snowflake precision in JSONB
            "label": r.label,
            "description": r.description,
            "emoji": r.emoji,
        }
        for r in body.roles
        if r.role_id.strip() and r.label.strip()
    ]
    panel.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(panel)
    return _serialize(panel)


@router.delete(
    "/{panel_id}",
    dependencies=[Depends(require_page_permission("staff.discord-config", "edit"))],
)
async def delete_role_panel(
    panel_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a panel from the database. The Discord message will become orphaned - delete it manually."""
    result = await session.execute(
        select(RolePanel).where(
            RolePanel.panel_id == panel_id, RolePanel.guild_id == _GUILD_ID
        )
    )
    panel = result.scalar_one_or_none()
    if panel is None:
        raise HTTPException(404, "Panel not found")

    await session.execute(delete(RolePanel).where(RolePanel.panel_id == panel_id))
    await session.commit()
    return {"deleted": panel_id}
