"""Clan router - public read endpoints for clan stats and activity."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Never

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import ClanStats, Config, Event, Leaderboard, Metric, User
from app.dependencies import get_current_user, get_session, get_valkey
from app.services.competitions import (
    CreateCompetitionInput,
    EditCompetitionInput,
    create_competition,
    delete_competition,
    edit_competition,
)
from app.services.http import WiseOldManHandler
from app.services.page_permissions import require_page_permission

router = APIRouter(prefix="/clan", tags=["clan"])

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_GROUP_KEY = os.getenv("WOM_GROUP_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")

_RAID_METRICS = [
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert_mode",
]


_KC_METRICS: dict[str, str] = {
    "abyssal_sire": "Abyssal Sire",
    "alchemical_hydra": "Alchemical Hydra",
    "amoxliatl": "Amoxliatl",
    "araxxor": "Araxxor",
    "artio": "Artio",
    "barrows_chests": "Barrows",
    "bryophyta": "Bryophyta",
    "callisto": "Callisto",
    "calvarion": "Calvar'ion",
    "cerberus": "Cerberus",
    "chambers_of_xeric": "Chambers of Xeric",
    "chambers_of_xeric_challenge_mode": "CoX: Challenge Mode",
    "chaos_elemental": "Chaos Elemental",
    "chaos_fanatic": "Chaos Fanatic",
    "commander_zilyana": "Commander Zilyana",
    "corporeal_beast": "Corporeal Beast",
    "crazy_archaeologist": "Crazy Archaeologist",
    "dagannoth_prime": "Dagannoth Prime",
    "dagannoth_rex": "Dagannoth Rex",
    "dagannoth_supreme": "Dagannoth Supreme",
    "deranged_archaeologist": "Deranged Archaeologist",
    "duke_sucellus": "Duke Sucellus",
    "general_graardor": "General Graardor",
    "giant_mole": "Giant Mole",
    "grotesque_guardians": "Grotesque Guardians",
    "hespori": "Hespori",
    "kalphite_queen": "Kalphite Queen",
    "king_black_dragon": "King Black Dragon",
    "kraken": "Kraken",
    "kree_arra": "Kree'arra",
    "kril_tsutsaroth": "K'ril Tsutsaroth",
    "lunar_chests": "Lunar Chests",
    "mimic": "Mimic",
    "nex": "Nex",
    "nightmare": "Nightmare",
    "obor": "Obor",
    "phantom_muspah": "Phantom Muspah",
    "phosanis_nightmare": "Phosani's Nightmare",
    "scurrius": "Scurrius",
    "skotizo": "Skotizo",
    "sol_heredit": "Sol Heredit",
    "spindel": "Spindel",
    "tempoross": "Tempoross",
    "the_corrupted_gauntlet": "The Corrupted Gauntlet",
    "the_gauntlet": "The Gauntlet",
    "the_hueycoatl": "The Hueycoatl",
    "the_leviathan": "The Leviathan",
    "the_whisperer": "The Whisperer",
    "theatre_of_blood": "Theatre of Blood",
    "theatre_of_blood_hard_mode": "ToB: Hard Mode",
    "thermonuclear_smoke_devil": "Thermonuclear Smoke Devil",
    "tombs_of_amascut": "Tombs of Amascut",
    "tombs_of_amascut_expert_mode": "ToA: Expert Mode",
    "tzkal_zuk": "TzKal-Zuk",
    "tztok_jad": "TzTok-Jad",
    "vardorvis": "Vardorvis",
    "venenatis": "Venenatis",
    "vetion": "Vet'ion",
    "vorkath": "Vorkath",
    "wintertodt": "Wintertodt",
    "zalcano": "Zalcano",
    "zulrah": "Zulrah",
}
_KC_FRESH_KEY = "clan:kc_fresh"
_KC_STALE_KEY = "clan:kc_stale"
_KC_LOCK_KEY = "clan:kc_lock"
_KC_FRESH_TTL = 15 * 60
_KC_STALE_TTL = 48 * 60 * 60
_KC_LOCK_TTL = 300

_LEAGUES_FRESH_KEY = "clan:leagues_fresh"
_LEAGUES_STALE_KEY = "clan:leagues_stale"
_LEAGUES_LOCK_KEY = "clan:leagues_lock"
_LEAGUES_FRESH_TTL = 15 * 60
_LEAGUES_STALE_TTL = 48 * 60 * 60
_LEAGUES_LOCK_TTL = 60

_NC_FRESH_KEY = "clan:name_changes_fresh"
_NC_STALE_KEY = "clan:name_changes_stale"
_NC_LOCK_KEY = "clan:name_changes_lock"
_NC_FRESH_TTL = 15 * 60
_NC_STALE_TTL = 6 * 60 * 60
_NC_LOCK_TTL = 60

_COMPS_FRESH_KEY = "clan:competitions_fresh"
_COMPS_STALE_KEY = "clan:competitions_stale"
_COMPS_LOCK_KEY = "clan:competitions_lock"
_COMPS_FRESH_TTL = 5 * 60
_COMPS_STALE_TTL = 2 * 60 * 60
_COMPS_LOCK_TTL = 120

_COMP_METRIC_MAP_KEY = "competition_metric_map"
_GLOBAL_GUILD_ID = 0

# Per-(comp_id, metric) cache: TTLs vary by competition status
_COMP_METRIC_ONGOING_FRESH_TTL = 5 * 60
_COMP_METRIC_UPCOMING_FRESH_TTL = 15 * 60
_COMP_METRIC_FINISHED_FRESH_TTL = 60 * 60
_COMP_METRIC_STALE_TTL = 2 * 60 * 60
_COMP_METRIC_LOCK_TTL = 60
_COMP_OVERTIME_LOCK_TTL = 60


def _comp_metric_keys(comp_id: int, metric: str) -> tuple[str, str, str]:
    base = f"clan:comp:{comp_id}:metric:{metric}"
    return f"{base}:fresh", f"{base}:stale", f"{base}:lock"


def _comp_metric_fresh_ttl(status: str) -> int:
    if status == "ongoing":
        return _COMP_METRIC_ONGOING_FRESH_TTL
    if status == "upcoming":
        return _COMP_METRIC_UPCOMING_FRESH_TTL
    return _COMP_METRIC_FINISHED_FRESH_TTL


def _comp_overtime_keys(comp_id: int, metric: str) -> tuple[str, str, str]:
    base = f"clan:comp:{comp_id}:overtime:{metric}"
    return f"{base}:fresh", f"{base}:stale", f"{base}:lock"


async def _build_kc_cache(valkey: Valkey) -> None:
    """Sequential, rate-limit-aware population of the KC leaderboard cache."""
    acquired = await valkey.set(_KC_LOCK_KEY, "1", ex=_KC_LOCK_TTL, nx=True)
    if not acquired:
        return

    try:
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            timeout=15.0,
        ) as wom:
            out: list[dict] = []
            for metric, display_name in _KC_METRICS.items():
                entries = await wom.fetch_kc_metric(_WOM_GROUP_ID, metric)
                if entries:
                    out.append(
                        {
                            "metric": metric,
                            "display_name": display_name,
                            "entries": entries,
                        }
                    )

        if out:
            payload = json.dumps(out)
            await valkey.setex(_KC_FRESH_KEY, _KC_FRESH_TTL, payload)
            await valkey.setex(_KC_STALE_KEY, _KC_STALE_TTL, payload)
    finally:
        await valkey.delete(_KC_LOCK_KEY)


async def _build_leagues_cache(valkey: Valkey) -> None:
    """Paginate WOM group hiscores for clue_scrolls_all and cache the ranked list."""
    acquired = await valkey.set(_LEAGUES_LOCK_KEY, "1", ex=_LEAGUES_LOCK_TTL, nx=True)
    if not acquired:
        return

    try:
        entries: list[dict] = []
        limit = 50
        offset = 0
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            timeout=15.0,
        ) as wom:
            while True:
                page = await wom.get_group_hiscores(
                    _WOM_GROUP_ID, "clue_scrolls_all", limit=limit, offset=offset
                )
                if not page:
                    break
                for e in page:
                    score = (e.get("data") or {}).get("score") or 0
                    if score > 0:
                        entries.append(
                            {
                                "player_name": e["player"]["displayName"],
                                "score": score,
                            }
                        )
                if len(page) < limit:
                    break
                offset += limit

        if entries:
            payload = json.dumps(entries)
            await valkey.setex(_LEAGUES_FRESH_KEY, _LEAGUES_FRESH_TTL, payload)
            await valkey.setex(_LEAGUES_STALE_KEY, _LEAGUES_STALE_TTL, payload)
    finally:
        await valkey.delete(_LEAGUES_LOCK_KEY)


_DROP_MIN_VALUE = 2_000_000
_XP_MIN_MILESTONE = 15_000_000
_XP_STEP = 5_000_000


@router.get("/wom-stats")
async def wom_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return the latest WOM clan stat snapshot written by ClanStatsService."""
    result = await session.execute(select(ClanStats).where(ClanStats.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return {
            "member_count": 0,
            "total_xp": 0,
            "total_ehb": 0,
            "cox_kc": 0,
            "tob_kc": 0,
            "toa_kc": 0,
            "updated_at": None,
        }
    return {
        "member_count": row.member_count or 0,
        "total_xp": row.total_xp or 0,
        "total_ehb": row.total_ehb or 0,
        "cox_kc": row.cox_kc or 0,
        "tob_kc": row.tob_kc or 0,
        "toa_kc": row.toa_kc or 0,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _build_name_changes_cache(valkey: Valkey) -> None:
    """Hydrate name-changes cache. Lock is already held by the scheduling request."""
    logger.info("name-changes cache: hydrating from WOM (group={})", _WOM_GROUP_ID)
    try:
        wom = WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        )
        changes = await wom.get_group_name_changes(_WOM_GROUP_ID, limit=50)
        result = [
            {
                "old_name": c["oldName"],
                "new_name": c["newName"],
                "resolved_at": c.get("resolvedAt"),
            }
            for c in changes
            if c.get("status") == "approved"
        ]
        payload = json.dumps(result)
        await valkey.setex(_NC_FRESH_KEY, _NC_FRESH_TTL, payload)
        await valkey.setex(_NC_STALE_KEY, _NC_STALE_TTL, payload)
        logger.info("name-changes cache: wrote {} approved changes", len(result))
    except Exception as exc:
        logger.error("name-changes cache: hydration failed - {}", exc)
    finally:
        await valkey.delete(_NC_LOCK_KEY)


@router.get("/name-changes")
async def group_name_changes(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return recent approved WOM name changes. Stale-while-revalidate, 15 min fresh / 6 h stale."""
    fresh = await valkey.get(_NC_FRESH_KEY)
    if fresh:
        return json.loads(fresh)

    # Acquire lock here so only one request ever schedules the background task.
    # All other cache-miss requests see the lock, skip scheduling, and return stale.
    if await valkey.set(_NC_LOCK_KEY, "1", ex=_NC_LOCK_TTL, nx=True):
        logger.info("name-changes: cache miss - scheduling hydration")
        background_tasks.add_task(_build_name_changes_cache, valkey)
    else:
        logger.debug("name-changes: cache miss, hydration already scheduled")

    stale = await valkey.get(_NC_STALE_KEY)
    return json.loads(stale) if stale else []


@router.get("/stats")
async def clan_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return aggregate clan stats: total GP looted and total collection log items."""
    gp_result = await session.execute(
        select(func.coalesce(func.sum(Event.data["coin_value"].as_integer()), 0)).where(
            Event.type.in_(["loot", "loot_key", "clue_item"])
        )
    )
    total_gp = gp_result.scalar_one() or 0

    # Sum the highest known log_slots per player from events (includes unlinked accounts).
    per_player = (
        select(func.max(Event.data["log_slots"].as_integer()).label("max_slots"))
        .where(
            Event.type == "collection_log",
            Event.player_name.is_not(None),
            Event.is_league_world.is_(False),
        )
        .group_by(Event.player_name)
        .subquery()
    )
    cl_result = await session.execute(
        select(func.coalesce(func.sum(per_player.c.max_slots), 0))
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
        results.append(
            {
                "type": "drop",
                "player": row.player_name,
                "label": d.get("item_name", ""),
                "detail": d.get("source") or None,
                "value": d.get("coin_value", 0),
                "timestamp": row.timestamp.isoformat(),
            }
        )

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
        results.append(
            {
                "type": "level",
                "player": row.player_name,
                "label": "Total Level" if skill == "total" else skill,
                "detail": None,
                "value": d.get("new_level", 0),
                "timestamp": row.timestamp.isoformat(),
            }
        )

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
        results.append(
            {
                "type": "level",
                "player": row.player_name,
                "label": "Total Level",
                "detail": None,
                "value": d.get("new_level", 0),
                "timestamp": row.timestamp.isoformat(),
            }
        )

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
        results.append(
            {
                "type": "xp_milestone",
                "player": row.player_name,
                "label": d.get("skill", ""),
                "detail": None,
                "value": d.get("xp", 0),
                "timestamp": row.timestamp.isoformat(),
            }
        )

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


@router.get("/leaderboards")
async def clan_leaderboards(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Return all personal best entries from the leaderboards table, sorted by activity then time."""
    result = await session.execute(
        select(Leaderboard)
        .where(Leaderboard.time_seconds > 0)
        .order_by(
            Leaderboard.activity,
            Leaderboard.variant,
            Leaderboard.time_seconds,
        )
    )
    return [
        {
            "player_name": r.player_name,
            "activity": r.activity,
            "variant": r.variant,
            "time_seconds": r.time_seconds,
        }
        for r in result.scalars()
    ]


@router.get("/leaderboards/killcounts")
async def killcount_leaderboard(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Top-10 players per boss, served from cache.

    Fresh cache TTL is 15 minutes.  When it expires a background refresh is
    scheduled (rate-limit-aware, sequential WOM fetches).  While the refresh
    runs the stale cache (48 h) is returned so the page never shows empty data.
    """
    fresh = await valkey.get(_KC_FRESH_KEY)
    if fresh:
        return json.loads(fresh)

    background_tasks.add_task(_build_kc_cache, valkey)

    stale = await valkey.get(_KC_STALE_KEY)
    return json.loads(stale) if stale else []


@router.get("/leaderboards/leagues")
async def leagues_leaderboard(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return clan members ranked by total Clue Scrolls completed, served from cache.

    Same stale-while-revalidate pattern as killcounts: fresh for 15 min,
    stale fallback for 48 h while a background refresh runs.
    """
    fresh = await valkey.get(_LEAGUES_FRESH_KEY)
    if fresh:
        return json.loads(fresh)

    background_tasks.add_task(_build_leagues_cache, valkey)

    stale = await valkey.get(_LEAGUES_STALE_KEY)
    return json.loads(stale) if stale else []


@router.get("/leaderboards/collection-log")
async def collection_log_leaderboard(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return players ranked by collection log slots, sourced from all clog events.

    Uses the events table so unlinked players are included. For each player the
    highest log_slots value ever seen is used (events are monotonically increasing).
    Players who have opted out of stats tracking are excluded.
    """
    opt_out_result = await session.execute(
        select(func.lower(User.rsn)).where(
            User.stats_opt_out.is_(True), User.rsn.is_not(None)
        )
    )
    opt_out_rsns: set[str] = {row[0] for row in opt_out_result}

    global_max_result = await session.execute(
        select(func.max(Event.data["log_slots_max"].as_integer())).where(
            Event.type == "collection_log",
            Event.is_league_world.is_(False),
        )
    )
    global_slots_max: int = global_max_result.scalar_one_or_none() or 0

    slots_col = func.max(Event.data["log_slots"].as_integer())
    result = await session.execute(
        select(
            Event.player_name,
            slots_col.label("slots"),
        )
        .where(
            Event.type == "collection_log",
            Event.player_name.is_not(None),
            Event.is_league_world.is_(False),
        )
        .group_by(Event.player_name)
        .order_by(slots_col.desc().nulls_last())
    )
    return [
        {
            "player_name": r.player_name,
            "slots": r.slots or 0,
            "slots_max": global_slots_max,
        }
        for r in result
        if r.player_name and r.player_name.lower() not in opt_out_rsns
    ]


async def _build_metric_detail_cache(
    comp_id: int, metric: str, status: str, valkey: Valkey
) -> None:
    """Fetch competition details for a specific metric and write to Valkey cache."""
    fresh_key, stale_key, lock_key = _comp_metric_keys(comp_id, metric)
    logger.info("comp metric cache: hydrating comp={} metric={}", comp_id, metric)
    try:
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        ) as wom:
            data = await wom.get_competition_details(comp_id, metric=metric)

        starts_at = datetime.fromisoformat(data["startsAt"].replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(data["endsAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if now < starts_at:
            status = "upcoming"
        elif now <= ends_at:
            status = "ongoing"
        else:
            status = "finished"

        def _safe_num(v: object) -> int | float:
            return v if isinstance(v, (int, float)) else 0

        raw_parts: list[dict] = []
        for p in data.get("participations", []):
            progress = p.get("progress") or {}
            raw_parts.append(
                {
                    "player_name": p["player"]["displayName"],
                    "team_name": p.get("teamName"),
                    "gained": _safe_num(progress.get("gained")),
                    "start": _safe_num(progress.get("start")),
                    "end": _safe_num(progress.get("end")),
                }
            )

        raw_parts.sort(key=lambda x: x["gained"], reverse=True)
        for i, part in enumerate(raw_parts, 1):
            part["rank"] = i

        payload = json.dumps(
            {
                "id": data["id"],
                "title": data["title"],
                "metric": metric,
                "type": data.get("type", "classic"),
                "status": status,
                "startsAt": data["startsAt"],
                "endsAt": data["endsAt"],
                "participations": raw_parts,
            }
        )
        fresh_ttl = _comp_metric_fresh_ttl(status)
        await valkey.setex(fresh_key, fresh_ttl, payload)
        await valkey.setex(stale_key, _COMP_METRIC_STALE_TTL, payload)
        logger.info(
            "comp metric cache: wrote comp={} metric={} participants={}",
            comp_id,
            metric,
            len(raw_parts),
        )
    except Exception as exc:
        logger.error(
            "comp metric cache: hydration failed comp={} metric={} - {}",
            comp_id,
            metric,
            exc,
        )
    finally:
        await valkey.delete(lock_key)


async def _build_overtime_cache(
    comp_id: int, metric: str, status: str, valkey: Valkey
) -> None:
    """Fetch competition top-5 progress from WOM and write to Valkey cache."""
    fresh_key, stale_key, lock_key = _comp_overtime_keys(comp_id, metric)
    logger.info("comp overtime cache: hydrating comp={} metric={}", comp_id, metric)
    try:
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        ) as wom:
            raw = await wom.get_competition_top5_progress(comp_id, metric)

        series = [
            {
                "player_name": entry["player"]["displayName"],
                "history": [
                    {"date": h["date"], "value": h.get("gained", h.get("value", 0))}
                    for h in entry.get("history", [])
                ],
            }
            for entry in raw
            if entry.get("player") and entry.get("history") is not None
        ]

        payload = json.dumps({"comp_id": comp_id, "metric": metric, "series": series})
        fresh_ttl = _comp_metric_fresh_ttl(status)
        await valkey.setex(fresh_key, fresh_ttl, payload)
        await valkey.setex(stale_key, _COMP_METRIC_STALE_TTL, payload)
        logger.info(
            "comp overtime cache: wrote comp={} metric={} series={}",
            comp_id,
            metric,
            len(series),
        )
    except Exception as exc:
        logger.error(
            "comp overtime cache: hydration failed comp={} metric={} - {}",
            comp_id,
            metric,
            exc,
        )
    finally:
        await valkey.delete(lock_key)


async def _build_competitions_cache(valkey: Valkey) -> None:
    """Fetch all group competitions from WOM and write to Valkey cache. Lock already held by caller."""
    logger.info("competitions cache: hydrating from WOM (group={})", _WOM_GROUP_ID)
    try:
        wom = WiseOldManHandler(
            api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT
        )
        comps = await wom.get_all_group_competitions(_WOM_GROUP_ID)
        if comps:
            payload = json.dumps(comps)
            await valkey.setex(_COMPS_FRESH_KEY, _COMPS_FRESH_TTL, payload)
            await valkey.setex(_COMPS_STALE_KEY, _COMPS_STALE_TTL, payload)
            statuses: dict[str, int] = {}
            for c in comps:
                statuses[c["status"]] = statuses.get(c["status"], 0) + 1
            logger.info(
                "competitions cache: wrote {} competitions ({})",
                len(comps),
                ", ".join(f"{v} {k}" for k, v in statuses.items()),
            )
        else:
            logger.warning(
                "competitions cache: WOM returned empty list - cache not updated"
            )
    except Exception as exc:
        logger.error("competitions cache: hydration failed - {}", exc)
    finally:
        await valkey.delete(_COMPS_LOCK_KEY)


async def _invalidate_competitions_cache(valkey: Valkey) -> None:
    """Delete fresh cache + lock so the next request triggers a rebuild. Leaves stale intact."""
    await valkey.delete(_COMPS_FRESH_KEY)
    await valkey.delete(_COMPS_LOCK_KEY)
    logger.info("competitions cache: invalidated after write operation")


def _handle_wom_error(exc: httpx.HTTPStatusError) -> Never:
    status = exc.response.status_code
    try:
        detail = exc.response.json().get("message", str(exc))
    except Exception:
        detail = str(exc)
    if status == 400:
        raise HTTPException(400, f"WOM rejected request: {detail}")
    if status == 404:
        raise HTTPException(404, "Competition not found on WOM.")
    if status == 429:
        raise HTTPException(429, "WOM rate limit reached.")
    raise HTTPException(502, f"WOM upstream error: {detail}")


@router.get("/competitions")
async def list_competitions(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return all group competitions with derived status and WOM urls.

    Stale-while-revalidate: fresh for 5 min, stale fallback for 2 h while a
    background refresh runs. Never blocks the response on a WOM round-trip.
    """
    fresh = await valkey.get(_COMPS_FRESH_KEY)
    if fresh:
        logger.debug("competitions: serving from fresh cache")
        return json.loads(fresh)

    # Acquire lock here - only one request ever schedules hydration.
    if await valkey.set(_COMPS_LOCK_KEY, "1", ex=_COMPS_LOCK_TTL, nx=True):
        logger.info("competitions: cache miss - scheduling hydration")
        background_tasks.add_task(_build_competitions_cache, valkey)
    else:
        logger.debug("competitions: cache miss, hydration already scheduled")

    stale = await valkey.get(_COMPS_STALE_KEY)
    if stale:
        logger.info("competitions: serving stale cache while refresh runs")
        return json.loads(stale)

    logger.warning("competitions: no cache at all - returning empty list")
    return []


class CompetitionMetricMapBody(BaseModel):
    competition_id: int
    metrics: list[str]


@router.get("/competitions/metric-map")
async def get_competition_metric_map(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the staff-configured metric map: {comp_id: [metric, ...], ...}."""
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _COMP_METRIC_MAP_KEY,
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
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == _COMP_METRIC_MAP_KEY,
        )
    )
    current: dict = result.scalar_one_or_none() or {}
    current[str(body.competition_id)] = body.metrics

    stmt = (
        pg_insert(Config)
        .values(guild_id=_GLOBAL_GUILD_ID, key=_COMP_METRIC_MAP_KEY, value=current)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"],
            set_={"value": current},
        )
    )
    await session.execute(stmt)
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


@router.get("/competitions/{comp_id}/metric-detail")
async def competition_metric_detail(
    comp_id: int,
    background_tasks: BackgroundTasks,
    metric: str = Query(..., description="WOM metric key, e.g. 'woodcutting'"),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Return competition participant data for a specific metric, with stale-while-revalidate caching."""
    fresh_key, stale_key, lock_key = _comp_metric_keys(comp_id, metric)

    # Determine competition status for fresh TTL calculation
    status = "ongoing"
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == comp_id), None)
            if match:
                status = match.get("status", "ongoing")
            break

    fresh = await valkey.get(fresh_key)
    if fresh:
        return json.loads(fresh)

    if await valkey.set(lock_key, "1", ex=_COMP_METRIC_LOCK_TTL, nx=True):
        background_tasks.add_task(
            _build_metric_detail_cache, comp_id, metric, status, valkey
        )

    stale = await valkey.get(stale_key)
    if stale:
        return json.loads(stale)

    # No cache at all - fetch synchronously so the first request doesn't fail
    try:
        await _build_metric_detail_cache(comp_id, metric, status, valkey)
        fresh = await valkey.get(fresh_key)
        if fresh:
            return json.loads(fresh)
    except Exception as exc:
        logger.error("comp metric detail: sync fetch failed - {}", exc)

    raise HTTPException(status_code=503, detail="Competition data not yet available.")


@router.get("/competitions/{comp_id}/overtime")
async def competition_overtime(
    comp_id: int,
    background_tasks: BackgroundTasks,
    metric: str = Query(..., description="WOM metric key"),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Top-5 player progress over time for a specific metric. Stale-while-revalidate."""
    fresh_key, stale_key, lock_key = _comp_overtime_keys(comp_id, metric)

    status = "ongoing"
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == comp_id), None)
            if match:
                status = match.get("status", "ongoing")
            break

    fresh = await valkey.get(fresh_key)
    if fresh:
        return json.loads(fresh)

    if await valkey.set(lock_key, "1", ex=_COMP_OVERTIME_LOCK_TTL, nx=True):
        background_tasks.add_task(_build_overtime_cache, comp_id, metric, status, valkey)

    stale = await valkey.get(stale_key)
    if stale:
        return json.loads(stale)

    try:
        await _build_overtime_cache(comp_id, metric, status, valkey)
        fresh = await valkey.get(fresh_key)
        if fresh:
            return json.loads(fresh)
    except Exception as exc:
        logger.error("comp overtime: sync fetch failed - {}", exc)

    raise HTTPException(status_code=503, detail="Timeline data not yet available.")


@router.get("/competitions/{comp_id}")
async def competition_details(
    comp_id: int,
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Return full competition details with participant progress, served from cache."""
    # Look up metric from the list cache so WOM only returns progress for that metric.
    metric: str | None = None
    for cache_key in (_COMPS_FRESH_KEY, _COMPS_STALE_KEY):
        raw = await valkey.get(cache_key)
        if raw:
            comps: list[dict] = json.loads(raw)
            match = next((c for c in comps if c.get("id") == comp_id), None)
            if match:
                metric = match.get("metric") or None
            break

    wom = WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT)
    try:
        data = await wom.get_cached_competition(comp_id, metric=metric)
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
        "competition_url": f"https://wiseoldman.net/competitions/{comp_id}",
        "metric_url": f"https://wiseoldman.net/competitions/{comp_id}?metric={metric}",
        "participations": participations,
    }


@router.post(
    "/competitions",
    status_code=201,
    dependencies=[Depends(require_page_permission("staff.competitions", "create"))],
)
async def create_competition_endpoint(
    body: CreateCompetitionInput,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Create a group competition on WOM."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        result = await create_competition(
            body,
            group_id=_WOM_GROUP_ID,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
        return result
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)


@router.put(
    "/competitions/{comp_id}",
    dependencies=[Depends(require_page_permission("staff.competitions", "edit"))],
)
async def edit_competition_endpoint(
    comp_id: int,
    body: EditCompetitionInput,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Edit an existing group competition on WOM."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        result = await edit_competition(
            comp_id,
            body,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        WiseOldManHandler._comp_cache.pop(comp_id, None)
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
        return result
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)


@router.delete(
    "/competitions/{comp_id}",
    status_code=204,
    dependencies=[Depends(require_page_permission("staff.competitions", "delete"))],
)
async def delete_competition_endpoint(
    comp_id: int,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> None:
    """Delete a group competition on WOM."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        await delete_competition(
            comp_id,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        WiseOldManHandler._comp_cache.pop(comp_id, None)
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)


@router.get("/user-avatar/{user_id}")
async def user_avatar(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the stored Discord avatar URL for the given user ID."""
    result = await session.execute(
        select(User.discord_avatar_url).where(User.discord_user_id == user_id)
    )
    avatar_url = result.scalar_one_or_none()
    if not avatar_url:
        raise HTTPException(status_code=404, detail="Avatar not available.")
    return {"avatar_url": avatar_url}
