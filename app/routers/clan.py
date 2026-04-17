"""Clan router — public read endpoints for clan stats and activity."""

from __future__ import annotations

import asyncio
import json
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import Event, Leaderboard, Metric, User
from app.dependencies import get_current_user, get_session, get_valkey

router = APIRouter(prefix="/clan", tags=["clan"])

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_CACHE_KEY = "clan:wom_stats"
_WOM_TTL = 5 * 60  # 5 minutes

# Raid metric slugs on WOM (mirror OSRS hiscores activity names)
_RAID_METRICS = [
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert_mode",
]


async def _fetch_metric_total(client: httpx.AsyncClient, group_id: str, metric: str) -> int:
    """Sum `data.kills` across all group members for a single WOM metric."""
    total = 0
    limit = 50
    offset = 0
    while True:
        resp = await client.get(
            f"https://api.wiseoldman.net/v2/groups/{group_id}/hiscores",
            params={"metric": metric, "limit": limit, "offset": offset},
            headers={"User-Agent": "IronFoundry/1.0"},
        )
        if not resp.is_success:
            break
        page: list[dict] = resp.json()
        if not page:
            break
        for entry in page:
            total += entry.get("data", {}).get("kills", 0) or 0
        if len(page) < limit:
            break
        offset += limit
    return total

_KC_METRICS: dict[str, str] = {
    "abyssal_sire":                     "Abyssal Sire",
    "alchemical_hydra":                 "Alchemical Hydra",
    "amoxliatl":                        "Amoxliatl",
    "araxxor":                          "Araxxor",
    "artio":                            "Artio",
    "barrows_chests":                   "Barrows",
    "bryophyta":                        "Bryophyta",
    "callisto":                         "Callisto",
    "calvarion":                        "Calvar'ion",
    "cerberus":                         "Cerberus",
    "chambers_of_xeric":                "Chambers of Xeric",
    "chambers_of_xeric_challenge_mode": "CoX: Challenge Mode",
    "chaos_elemental":                  "Chaos Elemental",
    "chaos_fanatic":                    "Chaos Fanatic",
    "commander_zilyana":                "Commander Zilyana",
    "corporeal_beast":                  "Corporeal Beast",
    "crazy_archaeologist":              "Crazy Archaeologist",
    "dagannoth_prime":                  "Dagannoth Prime",
    "dagannoth_rex":                    "Dagannoth Rex",
    "dagannoth_supreme":                "Dagannoth Supreme",
    "deranged_archaeologist":           "Deranged Archaeologist",
    "duke_sucellus":                    "Duke Sucellus",
    "general_graardor":                 "General Graardor",
    "giant_mole":                       "Giant Mole",
    "grotesque_guardians":              "Grotesque Guardians",
    "hespori":                          "Hespori",
    "kalphite_queen":                   "Kalphite Queen",
    "king_black_dragon":                "King Black Dragon",
    "kraken":                           "Kraken",
    "kree_arra":                        "Kree'arra",
    "kril_tsutsaroth":                  "K'ril Tsutsaroth",
    "lunar_chests":                     "Lunar Chests",
    "mimic":                            "Mimic",
    "nex":                              "Nex",
    "nightmare":                        "Nightmare",
    "obor":                             "Obor",
    "phantom_muspah":                   "Phantom Muspah",
    "phosanis_nightmare":               "Phosani's Nightmare",
    "scurrius":                         "Scurrius",
    "skotizo":                          "Skotizo",
    "sol_heredit":                      "Sol Heredit",
    "spindel":                          "Spindel",
    "tempoross":                        "Tempoross",
    "the_corrupted_gauntlet":           "The Corrupted Gauntlet",
    "the_gauntlet":                     "The Gauntlet",
    "the_hueycoatl":                    "The Hueycoatl",
    "the_leviathan":                    "The Leviathan",
    "the_whisperer":                    "The Whisperer",
    "theatre_of_blood":                 "Theatre of Blood",
    "theatre_of_blood_hard_mode":       "ToB: Hard Mode",
    "thermonuclear_smoke_devil":        "Thermonuclear Smoke Devil",
    "tombs_of_amascut":                 "Tombs of Amascut",
    "tombs_of_amascut_expert_mode":     "ToA: Expert Mode",
    "tzkal_zuk":                        "TzKal-Zuk",
    "tztok_jad":                        "TzTok-Jad",
    "vardorvis":                        "Vardorvis",
    "venenatis":                        "Venenatis",
    "vetion":                           "Vet'ion",
    "vorkath":                          "Vorkath",
    "wintertodt":                       "Wintertodt",
    "zalcano":                          "Zalcano",
    "zulrah":                           "Zulrah",
}
_KC_FRESH_KEY  = "clan:kc_fresh"
_KC_STALE_KEY  = "clan:kc_stale"
_KC_LOCK_KEY   = "clan:kc_lock"
_KC_FRESH_TTL  = 15 * 60        # 15 minutes
_KC_STALE_TTL  = 48 * 60 * 60  # 48 hours
_KC_LOCK_TTL   = 300            # max time we expect the full refresh to take

_LEAGUES_FRESH_KEY = "clan:leagues_fresh"
_LEAGUES_STALE_KEY = "clan:leagues_stale"
_LEAGUES_LOCK_KEY  = "clan:leagues_lock"
_LEAGUES_FRESH_TTL = 15 * 60
_LEAGUES_STALE_TTL = 48 * 60 * 60
_LEAGUES_LOCK_TTL  = 60


async def _fetch_kc_metric(
    client: httpx.AsyncClient, group_id: str, metric: str, top_n: int = 10
) -> list[dict] | None:
    """Fetch top `top_n` players for one WOM metric, retrying once on 429.

    Returns None if the metric is unavailable or a non-retryable error occurs.
    After a successful response the caller should check rate-limit headers and
    sleep if the remaining quota is low.
    """
    for attempt in range(2):
        try:
            resp = await client.get(
                f"https://api.wiseoldman.net/v2/groups/{group_id}/hiscores",
                params={"metric": metric, "limit": top_n, "offset": 0},
                headers={"User-Agent": "IronFoundry/1.0"},
            )
        except Exception:
            return None

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            await asyncio.sleep(retry_after)
            continue

        if not resp.is_success:
            return None

        # Throttle proactively before the next request
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "100"))
        if remaining <= 5:
            reset_in = float(resp.headers.get("X-RateLimit-Reset", "2"))
            await asyncio.sleep(max(reset_in, 0.5))

        return [
            {"player_name": e["player"]["displayName"], "kills": e["data"]["kills"]}
            for e in resp.json()
            if (e.get("data", {}).get("kills") or 0) > 0
        ]

    return None  # both attempts exhausted


async def _build_kc_cache(valkey: Valkey) -> None:
    """Sequential, rate-limit-aware population of the KC leaderboard cache.

    Uses a Valkey lock so only one refresh runs at a time.
    On success both fresh (15 min) and stale (48 h) keys are updated.
    """
    acquired = await valkey.set(_KC_LOCK_KEY, "1", ex=_KC_LOCK_TTL, nx=True)
    if not acquired:
        return  # another refresh is already running

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            out: list[dict] = []
            for metric, display_name in _KC_METRICS.items():
                entries = await _fetch_kc_metric(client, _WOM_GROUP_ID, metric)
                if entries:
                    out.append({
                        "metric": metric,
                        "display_name": display_name,
                        "entries": entries,
                    })

        if out:
            payload = json.dumps(out)
            await valkey.setex(_KC_FRESH_KEY, _KC_FRESH_TTL, payload)
            await valkey.setex(_KC_STALE_KEY, _KC_STALE_TTL, payload)
    finally:
        await valkey.delete(_KC_LOCK_KEY)


async def _build_leagues_cache(valkey: Valkey) -> None:
    """Paginate WOM group hiscores for league_points and cache the ranked list."""
    acquired = await valkey.set(_LEAGUES_LOCK_KEY, "1", ex=_LEAGUES_LOCK_TTL, nx=True)
    if not acquired:
        return

    try:
        entries: list[dict] = []
        limit = 50
        offset = 0
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                try:
                    resp = await client.get(
                        f"https://api.wiseoldman.net/v2/groups/{_WOM_GROUP_ID}/hiscores",
                        params={"metric": "league_points", "limit": limit, "offset": offset},
                        headers={"User-Agent": "IronFoundry/1.0"},
                    )
                except Exception:
                    break

                if resp.status_code == 429:
                    await asyncio.sleep(float(resp.headers.get("Retry-After", "10")))
                    continue

                if not resp.is_success:
                    break

                page: list[dict] = resp.json()
                if not page:
                    break

                for e in page:
                    score = (e.get("data") or {}).get("score") or 0
                    if score > 0:
                        entries.append({
                            "player_name": e["player"]["displayName"],
                            "score": score,
                        })

                remaining = int(resp.headers.get("X-RateLimit-Remaining", "100"))
                if remaining <= 5:
                    await asyncio.sleep(float(resp.headers.get("X-RateLimit-Reset", "2")))

                if len(page) < limit:
                    break
                offset += limit

        if entries:
            payload = json.dumps(entries)
            await valkey.setex(_LEAGUES_FRESH_KEY, _LEAGUES_FRESH_TTL, payload)
            await valkey.setex(_LEAGUES_STALE_KEY, _LEAGUES_STALE_TTL, payload)
    finally:
        await valkey.delete(_LEAGUES_LOCK_KEY)


_DROP_MIN_VALUE = 2_000_000      # 2M gp
_XP_MIN_MILESTONE = 15_000_000   # 15M xp
_XP_STEP = 5_000_000             # every 5M xp


@router.get("/wom-stats")
async def wom_stats(valkey: Valkey = Depends(get_valkey)) -> dict:
    """Return WiseOldMan group summary (member count, total XP, total EHB).

    Cached in Valkey for 5 minutes to avoid hitting WOM's rate limit on every
    page load.
    """
    cached = await valkey.get(_WOM_CACHE_KEY)
    if cached:
        return json.loads(cached)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch group summary and all raid hiscores concurrently
        group_coro = client.get(
            f"https://api.wiseoldman.net/v2/groups/{_WOM_GROUP_ID}",
            headers={"User-Agent": "IronFoundry/1.0"},
        )
        raid_coros = [
            _fetch_metric_total(client, _WOM_GROUP_ID, m) for m in _RAID_METRICS
        ]
        group_resp, *raid_totals = await asyncio.gather(group_coro, *raid_coros, return_exceptions=True)

    if isinstance(group_resp, Exception) or not group_resp.is_success:
        if not isinstance(group_resp, Exception) and group_resp.status_code == 429:
            raise HTTPException(status_code=429, detail="WiseOldMan rate limit reached — try again shortly.")
        raise HTTPException(status_code=502, detail="Failed to fetch WiseOldMan data.")

    raw = group_resp.json()
    memberships = raw.get("memberships") or []

    def _safe_int(v: object) -> int:
        return v if isinstance(v, int) else 0

    metric_totals = {m: _safe_int(t) for m, t in zip(_RAID_METRICS, raid_totals)}

    result = {
        "member_count": raw.get("memberCount", 0),
        "total_xp": sum(m.get("player", {}).get("exp", 0) for m in memberships),
        "total_ehb": round(sum(m.get("player", {}).get("ehb", 0.0) for m in memberships)),
        "cox_kc": metric_totals["chambers_of_xeric"] + metric_totals["chambers_of_xeric_challenge_mode"],
        "tob_kc": metric_totals["theatre_of_blood"] + metric_totals["theatre_of_blood_hard_mode"],
        "toa_kc": metric_totals["tombs_of_amascut"] + metric_totals["tombs_of_amascut_expert_mode"],
    }
    await valkey.setex(_WOM_CACHE_KEY, _WOM_TTL, json.dumps(result))
    return result


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

    # Fresh miss — kick off a background refresh if none is running
    background_tasks.add_task(_build_kc_cache, valkey)

    # Return stale data while the refresh runs; empty list on first ever load
    stale = await valkey.get(_KC_STALE_KEY)
    return json.loads(stale) if stale else []


@router.get("/leaderboards/leagues")
async def leagues_leaderboard(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return clan members ranked by Leagues Points, served from cache.

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
async def collection_log_leaderboard(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Return players ranked by collection log slots, sourced from all clog events.

    Uses the events table so unlinked players are included. For each player the
    highest log_slots value ever seen is used (events are monotonically increasing).
    Players who have opted out of stats tracking are excluded.
    """
    # Opt-out list — keyed by lower-case RSN
    opt_out_result = await session.execute(
        select(func.lower(User.rsn)).where(
            User.stats_opt_out.is_(True), User.rsn.is_not(None)
        )
    )
    opt_out_rsns: set[str] = {row[0] for row in opt_out_result}

    # Global slots_max — the single highest value seen across all clog events
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
