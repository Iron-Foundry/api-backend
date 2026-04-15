"""Clan router — public read endpoints for clan stats and activity."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Metric, User
from app.dependencies import get_session

router = APIRouter(prefix="/clan", tags=["clan"])

_DISCORD_API = "https://discord.com/api/v10"
_DROP_MIN_VALUE = 2_000_000      # 2M gp
_XP_MIN_MILESTONE = 15_000_000   # 15M xp
_XP_STEP = 5_000_000             # every 5M xp


@router.get("/stats")
async def clan_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return aggregate clan stats: total GP looted and total collection log items."""
    gp_result = await session.execute(
        select(
            func.coalesce(
                func.sum(Event.data["coin_value"].as_integer()), 0
            )
        ).where(Event.type.in_(["loot", "loot_key", "clue_item"]))
    )
    total_gp = gp_result.scalar_one() or 0

    cl_result = await session.execute(
        select(func.coalesce(func.sum(User.collection_log_slots), 0))
    )
    collection_log_items = cl_result.scalar_one() or 0

    clog_result = await session.execute(
        select(Metric.count).where(Metric.id == "total_clogs")
    )
    total_clogs = clog_result.scalar_one_or_none() or 0

    return {
        "total_gp": total_gp,
        "collection_log_items": collection_log_items,
        "total_clogs": total_clogs,
    }


@router.get("/recent-achievements")
async def recent_achievements(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return recent notable clan achievements across drops, levels, and XP milestones.

    Filters applied:
    - Drops: coin_value >= 2M
    - Levels: 99s and Total Level events
    - XP milestones: >= 15M xp
    """
    results: list[dict] = []

    # Notable drops
    drop_result = await session.execute(
        select(Event)
        .where(
            Event.type.in_(["loot", "loot_key", "clue_item"]),
            Event.data["coin_value"].as_integer() >= _DROP_MIN_VALUE,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in drop_result.scalars():
        d = row.data or {}
        results.append({
            "type": "drop",
            "player": row.player_name,
            "label": d.get("item_name", ""),
            "detail": d.get("source") or None,
            "value": d.get("coin_value", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # 99s and Total Level milestones
    level_result = await session.execute(
        select(Event)
        .where(
            Event.type == "level",
            Event.data["new_level"].as_integer() == 99,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in level_result.scalars():
        d = row.data or {}
        skill = d.get("skill", "")
        results.append({
            "type": "level",
            "player": row.player_name,
            "label": "Total Level" if skill == "total" else skill,
            "detail": None,
            "value": d.get("new_level", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # Also total level events
    total_level_result = await session.execute(
        select(Event)
        .where(
            Event.type == "level",
            Event.data["skill"].as_string() == "total",
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in total_level_result.scalars():
        d = row.data or {}
        results.append({
            "type": "level",
            "player": row.player_name,
            "label": "Total Level",
            "detail": None,
            "value": d.get("new_level", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # XP milestones >= 15M (divisible by 5M)
    xp_result = await session.execute(
        select(Event)
        .where(
            Event.type == "xp_milestone",
            Event.data["xp"].as_integer() >= _XP_MIN_MILESTONE,
            func.mod(Event.data["xp"].as_integer(), _XP_STEP) == 0,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in xp_result.scalars():
        d = row.data or {}
        results.append({
            "type": "xp_milestone",
            "player": row.player_name,
            "label": d.get("skill", ""),
            "detail": None,
            "value": d.get("xp", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


@router.get("/user-avatar/{user_id}")
async def user_avatar(user_id: int) -> Response:
    """Proxy the Discord avatar image for the given user ID.

    Uses the bot token to resolve the avatar hash, fetches the image from the
    Discord CDN, and streams the bytes back so the browser never has to make
    a cross-origin request to the CDN directly.
    """
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Discord token not configured")

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{_DISCORD_API}/users/{user_id}",
            headers={"Authorization": f"Bot {token}"},
        )
        if user_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Discord user not found")
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Discord API error")

        data = user_resp.json()
        avatar = data.get("avatar")
        if avatar:
            cdn_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.webp?size=64"
        else:
            discriminator = int(data.get("discriminator", "0") or "0")
            index = (user_id >> 22) % 6 if discriminator == 0 else discriminator % 5
            cdn_url = f"https://cdn.discordapp.com/embed/avatars/{index}.png"

        img_resp = await client.get(cdn_url)

    content_type = img_resp.headers.get("content-type", "image/webp")
    return Response(
        content=img_resp.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
