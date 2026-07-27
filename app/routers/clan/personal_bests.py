from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Leaderboard
from app.dependencies import get_session

router = APIRouter()


@router.get("/personal-bests")
async def clan_personal_bests(
    limit: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return recent personal best events from current rank 1 holders per activity."""
    rank1_subq = (
        select(
            Leaderboard.activity,
            Leaderboard.variant,
            func.min(Leaderboard.time_seconds).label("best_time"),
        )
        .group_by(Leaderboard.activity, Leaderboard.variant)
        .subquery()
    )
    rank1_entries_subq = (
        select(
            func.lower(Leaderboard.player_name).label("player_lower"),
            Leaderboard.activity,
            Leaderboard.variant,
            Leaderboard.time_seconds,
        )
        .join(
            rank1_subq,
            (Leaderboard.activity == rank1_subq.c.activity)
            & (Leaderboard.variant == rank1_subq.c.variant)
            & (Leaderboard.time_seconds == rank1_subq.c.best_time),
        )
        .subquery()
    )

    result = await session.execute(
        select(
            Event.player_name,
            Event.timestamp,
            Event.data,
            rank1_entries_subq.c.time_seconds.label("rank1_time"),
        )
        .join(
            rank1_entries_subq,
            (func.lower(Event.player_name) == rank1_entries_subq.c.player_lower)
            & (Event.data["activity"].as_string() == rank1_entries_subq.c.activity)
            & (
                func.coalesce(Event.data["variant"].as_string(), "")
                == rank1_entries_subq.c.variant
            ),
        )
        .where(Event.type == "personal_best")
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )

    rows = result.all()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = row.data or {}
        out.append(
            {
                "player": row.player_name,
                "activity": d.get("activity", ""),
                "variant": d.get("variant") or "",
                "time_seconds": row.rank1_time,
                "timestamp": row.timestamp.isoformat(),
            }
        )
    return out
