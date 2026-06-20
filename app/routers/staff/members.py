from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge, PlayerRanking, Ticket, User, UserBadge
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
        stmt = stmt.where(
            User.rsn.ilike(pattern) | User.discord_username.ilike(pattern)
        )
    stmt = stmt.order_by(User.join_date.asc().nulls_last()).limit(limit)
    result = await session.execute(stmt)
    members: list[dict] = []
    for row in result:
        members.append(
            {
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
            }
        )
    return members


@router.get("/members/{discord_user_id}")
async def staff_member_detail(
    discord_user_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Full member detail for the sheet view. Requires staff.members read permission."""
    await require_rank("staff.members", "read", current_user, session)

    row = (
        await session.execute(
            select(User).where(User.discord_user_id == discord_user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found.")

    badge_rows = (
        await session.execute(
            select(Badge, UserBadge.assigned_at, UserBadge.assigned_by)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.discord_user_id == discord_user_id)
            .order_by(UserBadge.assigned_at.asc())
        )
    ).all()

    ranking = None
    if row.rsn:
        ranking_row = (
            await session.execute(
                select(PlayerRanking).where(PlayerRanking.rsn.ilike(row.rsn))
            )
        ).scalar_one_or_none()
        if ranking_row:
            ranking = {
                "rank": ranking_row.rank,
                "points": ranking_row.points,
                "boss_points": ranking_row.boss_points,
                "skill_points": ranking_row.skill_points,
                "updated_at": ranking_row.updated_at.isoformat(),
            }

    ticket_count = (
        await session.execute(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.creator_id == discord_user_id)
        )
    ).scalar_one()

    return {
        "discord_user_id": str(row.discord_user_id),
        "discord_username": row.discord_username,
        "discord_avatar_url": row.discord_avatar_url,
        "rsn": row.rsn,
        "clan_rank": row.clan_rank,
        "discord_roles": row.discord_roles,
        "stats_opt_out": row.stats_opt_out,
        "hide_presence_notifications": row.hide_presence_notifications,
        "join_date": row.join_date.isoformat() if row.join_date else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "total_loot_value": row.total_loot_value,
        "clan_donated": row.clan_donated,
        "collection_log_slots": row.collection_log_slots,
        "collection_log_slots_max": row.collection_log_slots_max,
        "recruited_by": str(row.recruited_by) if row.recruited_by else None,
        "referral_source": row.referral_source,
        "referral_detail": row.referral_detail,
        "key_is_active": row.key_is_active,
        "key_created_at": row.key_created_at.isoformat()
        if row.key_created_at
        else None,
        "key_expires_at": row.key_expires_at.isoformat()
        if row.key_expires_at
        else None,
        "temp_vc_lock_status": row.temp_vc_lock_status,
        "temp_vc_member_limit": row.temp_vc_member_limit,
        "temp_vc_bitrate": row.temp_vc_bitrate,
        "ticket_count": ticket_count,
        "badges": [
            {
                "badge_id": str(b.id),
                "name": b.name,
                "description": b.description,
                "icon": b.icon,
                "color": b.color,
                "text_color": b.text_color,
                "assigned_at": assigned_at.isoformat() if assigned_at else None,
            }
            for b, assigned_at, _ in badge_rows
        ],
        "ranking": ranking,
    }
