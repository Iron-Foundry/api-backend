from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceSignup, User
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._account_helpers import linked_accounts
from ._roster_helpers import entry_or_404, event_or_404

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


@router.get("/events/{event_id}/roster/candidates")
async def list_candidates(
    event_id: int,
    search: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> list[dict[str, Any]]:
    """Clan members not on this event's roster yet, for the add picker."""
    await event_or_404(session, event_id)
    taken = select(TileRaceSignup.discord_user_id).where(
        TileRaceSignup.event_id == event_id
    )
    stmt = select(User.discord_user_id, User.discord_username, User.rsn).where(
        User.discord_user_id.notin_(taken)
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            User.rsn.ilike(pattern) | User.discord_username.ilike(pattern)
        )
    rows = await session.execute(
        stmt.order_by(User.rsn.asc().nulls_last()).limit(limit)
    )
    return [
        {
            "discord_user_id": str(row.discord_user_id),
            "discord_username": row.discord_username,
            "rsn": row.rsn,
        }
        for row in rows
    ]


@router.get("/events/{event_id}/roster/{discord_user_id}/accounts")
async def list_member_accounts(
    event_id: int,
    discord_user_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> list[dict[str, Any]]:
    """The member's linked RSNs, for switching a signup made on the wrong one."""
    entry = await entry_or_404(session, event_id, discord_user_id)
    return [
        {
            "id": account.id,
            "rsn": account.rsn,
            "is_primary": account.is_primary,
            "in_use": account.id == entry.account_id,
        }
        for account in await linked_accounts(session, discord_user_id)
    ]
