from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import CompetitionSnapshot, Config, User
from app.dependencies import get_session, get_valkey
from app.services.page_permissions import require_page_permission

from ._comp_cache import _build_metric_detail_cache, _build_competitions_cache
from ._constants import (
    _COMP_METRIC_LOCK_TTL,
    _COMP_METRIC_MAP_KEY,
    _COMPS_FRESH_KEY,
    _COMPS_LOCK_KEY,
    _COMPS_LOCK_TTL,
    _COMPS_STALE_KEY,
    _GLOBAL_GUILD_ID,
    _WOM_API_KEY,
    _WOM_DISCORD_CONTACT,
)
from ._helpers import _comp_metric_keys

router = APIRouter()


class CompetitionMetricMapBody(BaseModel):
    competition_id: int
    metrics: list[str]


@router.get("/competitions")
async def list_competitions(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return all group competitions. Stale-while-revalidate: fresh 5 min, stale fallback 2 h."""
    fresh = await valkey.get(_COMPS_FRESH_KEY)
    if fresh:
        return json.loads(fresh)
    if await valkey.set(_COMPS_LOCK_KEY, "1", ex=_COMPS_LOCK_TTL, nx=True):
        logger.info("competitions: cache miss - scheduling hydration")
        background_tasks.add_task(_build_competitions_cache, valkey)
    else:
        logger.debug("competitions: cache miss, hydration already scheduled")
    stale = await valkey.get(_COMPS_STALE_KEY)
    if stale:
        return json.loads(stale)
    return []


@router.get("/competitions/metric-map")
async def get_competition_metric_map(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the staff-configured metric map: {comp_id: [metric, ...], ...}."""
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID, Config.key == _COMP_METRIC_MAP_KEY
        )
    )
    return result.scalar_one_or_none() or {}


@router.post(
    "/competitions/metric-map",
    dependencies=[Depends(require_page_permission("staff.competitions", "edit"))],
)
async def set_competition_metric_map(
    body: CompetitionMetricMapBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upsert the metric list for a competition. Senior staff only."""
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID, Config.key == _COMP_METRIC_MAP_KEY
        )
    )
    current: dict = result.scalar_one_or_none() or {}
    current[str(body.competition_id)] = body.metrics
    await session.execute(
        pg_insert(Config)
        .values(guild_id=_GLOBAL_GUILD_ID, key=_COMP_METRIC_MAP_KEY, value=current)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"], set_={"value": current}
        )
    )
    await session.commit()
    return current


@router.get("/competitions/participants")
async def list_competition_participants(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return all users with linked RSNs for competition participant autofill."""
    result = await session.execute(
        select(User.rsn, User.discord_username).where(User.rsn.is_not(None))
    )
    return [
        {"rsn": row.rsn, "discord_username": row.discord_username} for row in result
    ]


@router.get("/competitions/{competition_id}/metric-detail")
async def competition_metric_detail(
    competition_id: int,
    background_tasks: BackgroundTasks,
    metric: str = Query(..., description="WOM metric key, e.g. 'woodcutting'"),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Return competition participant data for a specific metric, with stale-while-revalidate caching."""
    fresh_key, stale_key, lock_key = _comp_metric_keys(competition_id, metric)
    status = "ongoing"
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == competition_id), None)
            if match:
                status = match.get("status", "ongoing")
            break

    fresh = await valkey.get(fresh_key)
    if fresh:
        return json.loads(fresh)

    if await valkey.set(lock_key, "1", ex=_COMP_METRIC_LOCK_TTL, nx=True):
        background_tasks.add_task(
            _build_metric_detail_cache, competition_id, metric, status, valkey
        )

    stale = await valkey.get(stale_key)
    if stale:
        return json.loads(stale)

    try:
        await _build_metric_detail_cache(competition_id, metric, status, valkey)
        fresh = await valkey.get(fresh_key)
        if fresh:
            return json.loads(fresh)
    except Exception as exc:
        logger.error("comp metric detail: sync fetch failed - {}", exc)

    raise HTTPException(status_code=503, detail="Competition data not yet available.")


@router.get("/competitions/{competition_id}/overtime")
async def competition_overtime(
    competition_id: int,
    metric: str = Query(..., description="WOM metric key"),
    limit: int = Query(5, ge=1, le=25, description="Max players to return"),
    valkey: Valkey = Depends(get_valkey),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Player progress over time, reconstructed from DB snapshots."""
    status = "ongoing"
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == competition_id), None)
            if match:
                status = match.get("status", "ongoing")
            break

    db_result = await session.execute(
        select(CompetitionSnapshot)
        .where(
            CompetitionSnapshot.comp_id == competition_id,
            CompetitionSnapshot.metric == metric,
        )
        .order_by(CompetitionSnapshot.captured_at.asc())
    )
    db_snaps = db_result.scalars().all()

    if db_snaps:
        age = datetime.now(timezone.utc) - db_snaps[-1].captured_at
        if status == "finished" or age < timedelta(minutes=35):
            players: dict[str, list[dict]] = {}
            for snap in db_snaps:
                for standing in snap.series:
                    name = standing["player_name"]
                    players.setdefault(name, []).append(
                        {
                            "date": snap.captured_at.isoformat(),
                            "value": standing["gained"],
                        }
                    )
            series = sorted(
                [{"player_name": n, "history": h} for n, h in players.items()],
                key=lambda p: p["history"][-1]["value"] if p["history"] else 0,
                reverse=True,
            )[:limit]
            return {"comp_id": competition_id, "metric": metric, "series": series}

    raise HTTPException(status_code=503, detail="Timeline data not yet available.")


@router.get("/competitions/{competition_id}")
async def competition_details(
    competition_id: int,
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Return full competition details with participant progress, served from cache."""
    from app.services.http import WiseOldManHandler, WomPriority
    import httpx

    metric: str | None = None
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == competition_id), None)
            if match:
                metric = match.get("metric") or None
            break

    wom = WiseOldManHandler(
        api_key=_WOM_API_KEY,
        discord_contact=_WOM_DISCORD_CONTACT,
        priority=WomPriority.HIGH,
    )
    try:
        data = await wom.get_cached_competition(competition_id, metric=metric)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Competition not found.")
        if exc.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="WiseOldMan rate limit reached - try again shortly.",
            )
        raise HTTPException(
            status_code=502, detail="Failed to fetch competition details."
        )

    starts_at = datetime.fromisoformat(data["startsAt"].replace("Z", "+00:00"))
    ends_at = datetime.fromisoformat(data["endsAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if now < starts_at:
        status = "upcoming"
    elif now <= ends_at:
        status = "ongoing"
    else:
        status = "finished"

    metric = data.get("metric", "")
    participations = [
        {
            "player_name": p["player"]["displayName"],
            "team_name": p.get("teamName"),
            "progress": p.get("progress", {}),
            "levels": p.get("levels", {}),
        }
        for p in data.get("participations", [])
    ]
    return {
        "id": data["id"],
        "title": data["title"],
        "metric": metric,
        "type": data.get("type"),
        "startsAt": data["startsAt"],
        "endsAt": data["endsAt"],
        "groupId": data.get("groupId"),
        "participantCount": len(participations),
        "score": data.get("score"),
        "status": status,
        "competition_url": f"https://wiseoldman.net/competitions/{competition_id}",
        "metric_url": f"https://wiseoldman.net/competitions/{competition_id}?metric={metric}",
        "participations": participations,
    }
