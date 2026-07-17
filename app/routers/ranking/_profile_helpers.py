from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge, Event, PlayerRanking, User, UserAccount, UserBadge
from app.routers.badges._helpers import serialize_badge

from ._achievements import ACHIEVEMENT_TYPES, build_achievement


class AccountRankingSchema(BaseModel):
    rsn: str
    rank: str
    points: int
    boss_points: int
    skill_points: int


class LatestAchievementSchema(BaseModel):
    type: str
    label: str
    detail: str | None
    timestamp: datetime


class PlayerProfileSchema(BaseModel):
    rsn: str
    discord_username: str | None
    discord_avatar_url: str | None
    join_date: datetime | None
    stats_opt_out: bool
    accounts: list[AccountRankingSchema]
    badges: list[dict]
    latest_achievement: LatestAchievementSchema | None


async def _load_linked_rsns(
    session: AsyncSession, discord_user_id: int | None, fallback_rsn: str
) -> list[str]:
    if discord_user_id is None:
        return [fallback_rsn]
    result = await session.execute(
        select(UserAccount.rsn).where(UserAccount.discord_user_id == discord_user_id)
    )
    return [r for r in result.scalars().all()] or [fallback_rsn]


async def _load_badges_and_achievement(
    session: AsyncSession, discord_user_id: int, linked_rsns: list[str]
) -> tuple[list[dict], LatestAchievementSchema | None]:
    badges_result = await session.execute(
        select(Badge)
        .join(UserBadge, UserBadge.badge_id == Badge.id)
        .where(UserBadge.discord_user_id == discord_user_id)
        .order_by(UserBadge.assigned_at)
    )
    badges = [serialize_badge(b) for b in badges_result.scalars().all()]

    rsn_lower = [r.lower() for r in linked_rsns]
    events_result = await session.execute(
        select(Event)
        .where(
            Event.type.in_(ACHIEVEMENT_TYPES),
            func.lower(Event.player_name).in_(rsn_lower),
        )
        .order_by(Event.timestamp.desc())
        .limit(20)
    )
    latest_achievement: LatestAchievementSchema | None = None
    for row in events_result.scalars().all():
        built = build_achievement(row)
        if built is not None:
            latest_achievement = LatestAchievementSchema(**built)
            break

    return badges, latest_achievement


async def get_player_profile(
    rsn: str, session: AsyncSession
) -> PlayerProfileSchema | None:
    result = await session.execute(
        select(PlayerRanking).where(PlayerRanking.rsn.ilike(rsn))
    )
    player = result.scalar_one_or_none()
    if player is None:
        return None

    discord_user_id = player.discord_user_id
    user = None
    if discord_user_id is not None:
        user_result = await session.execute(
            select(User).where(User.discord_user_id == discord_user_id)
        )
        user = user_result.scalar_one_or_none()

    linked_rsns = await _load_linked_rsns(session, discord_user_id, player.rsn)

    rankings_result = await session.execute(
        select(PlayerRanking).where(PlayerRanking.rsn.in_(linked_rsns))
    )
    accounts = [
        AccountRankingSchema(
            rsn=r.rsn,
            rank=r.rank,
            points=r.points,
            boss_points=r.boss_points,
            skill_points=r.skill_points,
        )
        for r in rankings_result.scalars().all()
    ]

    badges: list[dict] = []
    latest_achievement: LatestAchievementSchema | None = None
    if discord_user_id is not None:
        badges, latest_achievement = await _load_badges_and_achievement(
            session, discord_user_id, linked_rsns
        )

    return PlayerProfileSchema(
        rsn=player.rsn,
        discord_username=user.discord_username if user else None,
        discord_avatar_url=user.discord_avatar_url if user else None,
        join_date=user.join_date if user else None,
        stats_opt_out=user.stats_opt_out if user else False,
        accounts=accounts,
        badges=badges,
        latest_achievement=latest_achievement,
    )
