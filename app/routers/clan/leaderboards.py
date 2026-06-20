from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

import json

from app.db.models import Event, Leaderboard, User
from app.dependencies import get_session, get_valkey

from ._constants import (
    _KC_FRESH_KEY,
    _KC_STALE_KEY,
    _LEAGUES_FRESH_KEY,
    _LEAGUES_STALE_KEY,
)
from ._helpers import _enrich_with_ranks
from ._leaderboard_cache import _build_kc_cache, _build_leagues_cache

router = APIRouter()


def _dedup_flat(entries: list[dict]) -> list[dict]:
    """Remove entries where the same discord_user_id already appeared. Assumes entries are pre-sorted best-first."""
    seen: set[int] = set()
    out: list[dict] = []
    for e in entries:
        uid = e.pop("_discord_user_id", None)
        if uid is None or uid not in seen:
            if uid is not None:
                seen.add(uid)
            out.append(e)
    return out


def _dedup_pb(entries: list[dict]) -> list[dict]:
    """Remove PB entries where same discord_user_id already holds a time in the same activity+variant. Assumes sorted by time ASC."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in entries:
        uid = e.pop("_discord_user_id", None)
        if uid is not None:
            key = (uid, e["activity"], e["variant"])
            if key in seen:
                continue
            seen.add(key)
        out.append(e)
    return out


@router.get("/leaderboards")
async def clan_leaderboards(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Return all personal best entries from the leaderboards table, sorted by activity then time."""
    result = await session.execute(
        select(Leaderboard)
        .where(Leaderboard.time_seconds > 0)
        .order_by(Leaderboard.activity, Leaderboard.variant, Leaderboard.time_seconds)
    )
    rows = result.scalars().all()
    result_dicts = [
        {
            "player_name": r.player_name,
            "activity": r.activity,
            "variant": r.variant,
            "time_seconds": r.time_seconds,
            "clan_rank": None,
            "discord_rank": None,
        }
        for r in rows
    ]
    entries_by_name: dict[str, list[dict]] = {}
    for e in result_dicts:
        if e["player_name"]:
            entries_by_name.setdefault(e["player_name"].lower(), []).append(e)
    await _enrich_with_ranks(entries_by_name, session)
    return _dedup_pb(result_dicts)


@router.get("/leaderboards/killcounts")
async def killcount_leaderboard(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Top players per boss, served from cache. Fresh 15 min, stale fallback 48 h."""
    fresh = await valkey.get(_KC_FRESH_KEY)
    data: list[dict] = json.loads(fresh) if fresh else []
    if not data:
        background_tasks.add_task(_build_kc_cache, valkey)
        stale = await valkey.get(_KC_STALE_KEY)
        data = json.loads(stale) if stale else []
    if data:
        entries_by_name: dict[str, list[dict]] = {}
        for boss in data:
            for e in boss.get("entries", []):
                entries_by_name.setdefault(e["player_name"].lower(), []).append(e)
        await _enrich_with_ranks(entries_by_name, session)
        for boss in data:
            boss["entries"] = _dedup_flat(boss.get("entries", []))
    return data


@router.get("/leaderboards/leagues")
async def leagues_leaderboard(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Clan members ranked by Clue Scrolls completed, served from cache. Fresh 15 min, stale 48 h."""
    fresh = await valkey.get(_LEAGUES_FRESH_KEY)
    data: list[dict] = json.loads(fresh) if fresh else []
    if not data:
        background_tasks.add_task(_build_leagues_cache, valkey)
        stale = await valkey.get(_LEAGUES_STALE_KEY)
        data = json.loads(stale) if stale else []
    if data:
        entries_by_name = {e["player_name"].lower(): [e] for e in data}
        await _enrich_with_ranks(entries_by_name, session)
        data = _dedup_flat(data)
    return data


@router.get("/leaderboards/collection-log")
async def collection_log_leaderboard(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Players ranked by collection log slots. Excludes opted-out players."""
    opt_out_result = await session.execute(
        select(func.lower(User.rsn)).where(
            User.stats_opt_out.is_(True), User.rsn.is_not(None)
        )
    )
    opt_out_rsns: set[str] = {row[0] for row in opt_out_result}

    global_max_result = await session.execute(
        select(func.max(Event.data["log_slots_max"].as_integer())).where(
            Event.type == "collection_log", Event.is_league_world.is_(False)
        )
    )
    global_slots_max: int = global_max_result.scalar_one_or_none() or 0

    slots_col = func.max(Event.data["log_slots"].as_integer())
    result = await session.execute(
        select(Event.player_name, slots_col.label("slots"))
        .where(
            Event.type == "collection_log",
            Event.player_name.is_not(None),
            Event.is_league_world.is_(False),
        )
        .group_by(Event.player_name)
        .order_by(slots_col.desc().nulls_last())
    )
    rows = [
        r for r in result if r.player_name and r.player_name.lower() not in opt_out_rsns
    ]
    result_dicts = [
        {
            "player_name": r.player_name,
            "slots": r.slots or 0,
            "slots_max": global_slots_max,
            "clan_rank": None,
            "discord_rank": None,
        }
        for r in rows
    ]
    entries_by_name_clog: dict[str, list[dict]] = {}
    for e in result_dicts:
        if e["player_name"]:
            entries_by_name_clog.setdefault(e["player_name"].lower(), []).append(e)
    await _enrich_with_ranks(entries_by_name_clog, session)
    return _dedup_flat(result_dicts)
