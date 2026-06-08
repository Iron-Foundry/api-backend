from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.dependencies import get_current_user, get_session

from ._helpers import require_rank

router = APIRouter()


@router.get("/members")
async def staff_members(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    search: str | None = None,
    limit: int = Query(default=1000, ge=1, le=2000),
) -> list[dict]:
    """Return all member profiles. Requires staff.members read permission."""
    await require_rank("staff.members", "read", current_user, session)
    stmt = select(
        User.discord_user_id,
        User.discord_username,
        User.discord_avatar_url,
        User.rsn,
        User.clan_rank,
        User.discord_roles,
        User.stats_opt_out,
        User.join_date,
        User.created_at,
        User.total_loot_value,
        User.collection_log_slots,
        User.recruited_by,
        User.key_is_active,
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(User.rsn.ilike(pattern) | User.discord_username.ilike(pattern))
    stmt = stmt.order_by(User.join_date.asc().nulls_last()).limit(limit)
    result = await session.execute(stmt)
    members: list[dict] = []
    for row in result:
        members.append({
            "discord_user_id": str(row.discord_user_id),
            "discord_username": row.discord_username,
            "discord_avatar_url": row.discord_avatar_url,
            "rsn": row.rsn,
            "clan_rank": row.clan_rank,
            "discord_roles": row.discord_roles,
            "stats_opt_out": row.stats_opt_out,
            "join_date": row.join_date.isoformat() if row.join_date else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "total_loot_value": row.total_loot_value,
            "collection_log_slots": row.collection_log_slots,
            "recruited_by": str(row.recruited_by) if row.recruited_by else None,
            "key_is_active": row.key_is_active,
        })
    return members
