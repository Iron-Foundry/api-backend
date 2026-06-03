"""Frenzy router - PVM Frenzy event management and public display."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import FrenzyEvent, FrenzySubmission, FrenzyTemplate, FrenzyTemplateVersion, FrenzyTeam, User
from app.dependencies import get_current_user, get_optional_user, get_session, get_valkey
from app.services.http import WiseOldManHandler
from app.services.page_permissions import require_page_permission

router = APIRouter(prefix="/frenzy", tags=["frenzy"])

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")

# Leaderboard cache
_LB_FRESH_KEY = "frenzy:leaderboards:fresh"
_LB_STALE_KEY = "frenzy:leaderboards:stale"
_LB_LOCK_KEY = "frenzy:leaderboards:lock"
_LB_FRESH_TTL = 5 * 60
_LB_STALE_TTL = 2 * 60 * 60
_LB_LOCK_TTL = 120

# OSRS reference data cache
_ITEMS_KEY = "osrs:items:mapping"
_BOSSES_KEY = "osrs:bosses:list"
_ACTIVITIES_KEY = "osrs:activities:list"
_OSRS_REF_TTL = 24 * 60 * 60

# Canonical boss list (WOM slugs → display names + wiki icon slug)
_BOSS_METRICS: dict[str, tuple[str, str]] = {
    "abyssal_sire": ("Abyssal Sire", "Abyssal_Sire"),
    "alchemical_hydra": ("Alchemical Hydra", "Alchemical_Hydra"),
    "amoxliatl": ("Amoxliatl", "Amoxliatl"),
    "araxxor": ("Araxxor", "Araxxor"),
    "artio": ("Artio", "Artio"),
    "barrows_chests": ("Barrows Chests", "Barrows"),
    "bryophyta": ("Bryophyta", "Bryophyta"),
    "callisto": ("Callisto", "Callisto"),
    "calvarion": ("Calvar'ion", "Calvar%27ion"),
    "cerberus": ("Cerberus", "Cerberus"),
    "chambers_of_xeric": ("Chambers of Xeric", "Chambers_of_Xeric"),
    "chambers_of_xeric_challenge_mode": ("Chambers of Xeric: CM", "Chambers_of_Xeric"),
    "chaos_elemental": ("Chaos Elemental", "Chaos_Elemental"),
    "chaos_fanatic": ("Chaos Fanatic", "Chaos_Fanatic"),
    "commander_zilyana": ("Commander Zilyana", "Commander_Zilyana"),
    "corporeal_beast": ("Corporeal Beast", "Corporeal_Beast"),
    "crazy_archaeologist": ("Crazy Archaeologist", "Crazy_Archaeologist"),
    "dagannoth_prime": ("Dagannoth Prime", "Dagannoth_Prime"),
    "dagannoth_rex": ("Dagannoth Rex", "Dagannoth_Rex"),
    "dagannoth_supreme": ("Dagannoth Supreme", "Dagannoth_Supreme"),
    "deranged_archaeologist": ("Deranged Archaeologist", "Deranged_Archaeologist"),
    "duke_sucellus": ("Duke Sucellus", "Duke_Sucellus"),
    "general_graardor": ("General Graardor", "General_Graardor"),
    "giant_mole": ("Giant Mole", "Giant_Mole"),
    "grotesque_guardians": ("Grotesque Guardians", "Grotesque_Guardians"),
    "hespori": ("Hespori", "Hespori"),
    "kalphite_queen": ("Kalphite Queen", "Kalphite_Queen"),
    "king_black_dragon": ("King Black Dragon", "King_Black_Dragon"),
    "kraken": ("Kraken", "Kraken"),
    "kree_arra": ("Kree'arra", "Kree%27arra"),
    "kril_tsutsaroth": ("K'ril Tsutsaroth", "K%27ril_Tsutsaroth"),
    "lunar_chests": ("Lunar Chests", "Lunar_Chests"),
    "mimic": ("Mimic", "Mimic_(monster)"),
    "nex": ("Nex", "Nex"),
    "nightmare": ("Nightmare", "The_Nightmare"),
    "obor": ("Obor", "Obor"),
    "phantom_muspah": ("Phantom Muspah", "Phantom_Muspah"),
    "phosanis_nightmare": ("Phosani's Nightmare", "Phosani%27s_Nightmare"),
    "royal_titans": ("Royal Titans", "Royal_Titans"),
    "sarachnis": ("Sarachnis", "Sarachnis"),
    "scorpia": ("Scorpia", "Scorpia"),
    "scurrius": ("Scurrius", "Scurrius"),
    "skotizo": ("Skotizo", "Skotizo"),
    "sol_heredit": ("Sol Heredit", "Sol_Heredit"),
    "spindel": ("Spindel", "Spindel"),
    "tempoross": ("Tempoross", "Tempoross"),
    "the_corrupted_gauntlet": ("The Corrupted Gauntlet", "The_Corrupted_Gauntlet"),
    "the_gauntlet": ("The Gauntlet", "The_Gauntlet"),
    "the_hueycoatl": ("The Hueycoatl", "The_Hueycoatl"),
    "the_leviathan": ("The Leviathan", "The_Leviathan"),
    "the_whisperer": ("The Whisperer", "The_Whisperer"),
    "theatre_of_blood": ("Theatre of Blood", "Theatre_of_Blood"),
    "theatre_of_blood_hard_mode": ("Theatre of Blood: HM", "Theatre_of_Blood"),
    "thermonuclear_smoke_devil": ("Thermonuclear Smoke Devil", "Thermonuclear_Smoke_Devil"),
    "tombs_of_amascut": ("Tombs of Amascut", "Tombs_of_Amascut"),
    "tombs_of_amascut_expert_mode": ("Tombs of Amascut: Expert", "Tombs_of_Amascut"),
    "tzkal_zuk": ("TzKal-Zuk", "TzKal-Zuk"),
    "tztok_jad": ("TzTok-Jad", "TzTok-Jad"),
    "vardorvis": ("Vardorvis", "Vardorvis"),
    "venenatis": ("Venenatis", "Venenatis"),
    "vetion": ("Vet'ion", "Vet%27ion"),
    "vorkath": ("Vorkath", "Vorkath"),
    "wintertodt": ("Wintertodt", "Wintertodt"),
    "yama": ("Yama", "Yama"),
    "zalcano": ("Zalcano", "Zalcano"),
    "zulrah": ("Zulrah", "Zulrah"),
}

# Activities/minigames tracked by WOM
_ACTIVITY_METRICS: dict[str, tuple[str, str]] = {
    "bounty_hunter_hunter": ("Bounty Hunter - Hunter", "Bounty_Hunter"),
    "bounty_hunter_rogue": ("Bounty Hunter - Rogue", "Bounty_Hunter"),
    "clue_scrolls_all": ("Clue Scrolls (All)", "Clue_scroll"),
    "clue_scrolls_beginner": ("Clue Scrolls (Beginner)", "Clue_scroll_(beginner)"),
    "clue_scrolls_easy": ("Clue Scrolls (Easy)", "Clue_scroll_(easy)"),
    "clue_scrolls_medium": ("Clue Scrolls (Medium)", "Clue_scroll_(medium)"),
    "clue_scrolls_hard": ("Clue Scrolls (Hard)", "Clue_scroll_(hard)"),
    "clue_scrolls_elite": ("Clue Scrolls (Elite)", "Clue_scroll_(elite)"),
    "clue_scrolls_master": ("Clue Scrolls (Master)", "Clue_scroll_(master)"),
    "colosseum_glory": ("Colosseum Glory", "Fortis_Colosseum"),
    "collections_logged": ("Collections Logged", "Collection_log"),
    "combat_achievement_points": ("Combat Achievement Points", "Combat_Achievements"),
    "gotr_runes_crafted": ("GOTR Runes Crafted", "Guardians_of_the_Rift"),
    "guardians_of_the_rift": ("Guardians of the Rift", "Guardians_of_the_Rift"),
    "last_man_standing": ("Last Man Standing", "Last_Man_Standing"),
    "league_points": ("League Points", "Trailblazer_Reloaded_League"),
    "nightmare_zone": ("Nightmare Zone", "Nightmare_Zone"),
    "pvp_arena_rank": ("PvP Arena", "PvP_Arena"),
    "rifts_closed": ("Rifts Closed", "Guardians_of_the_Rift"),
    "soul_wars_zeal": ("Soul Wars Zeal", "Soul_Wars"),
    "tempoross": ("Tempoross", "Tempoross"),
    "theatre_of_blood_hard_mode": ("ToB: Hard Mode", "Theatre_of_Blood"),
    "wintertodt": ("Wintertodt", "Wintertodt"),
}

_WIKI_IMAGE_BASE = "https://oldschool.runescape.wiki/images"


def _wiki_icon(slug: str) -> str:
    return f"{_WIKI_IMAGE_BASE}/{slug}.png"


# ---------------------------------------------------------------------------
# Scoring helpers (mirrors web-app/src/lib/frenzy.ts)
# ---------------------------------------------------------------------------

def _calc_item_points(item: dict, obtained: int) -> float:
    pts = 0.0
    base_pts: float = item.get("points", 0)
    dup_pts: float = base_pts / 2
    required: int = item.get("required", 1)
    dup_required: int = item.get("duplicate_required", 1)

    if obtained >= required:
        pts += base_pts
    elif required == 2 and obtained == 1:
        pts += base_pts / 2

    beyond = obtained - required
    if beyond >= dup_required:
        pts += dup_pts
    elif dup_required == 2 and beyond == 1:
        pts += dup_pts / 2

    return pts


def _calc_tier_entry_points(entry: dict, current_value: float) -> float:
    tiers_done = sum(
        1
        for t in ["tier1", "tier2", "tier3", "tier4"]
        if current_value >= entry.get(t, 0)
    )
    base = entry.get("point_step", 0) * tiers_done
    if current_value >= entry.get("tier4", 0) and tiers_done == 4:
        return base * entry.get("multiplier", 1)
    return float(base)


def _is_multiplier_unlocked(mult: dict, item_progress: dict) -> bool:
    return all(item_progress.get(r, 0) > 0 for r in mult.get("requirement", []))


def _compute_team_scores(template: FrenzyTemplate, team: FrenzyTeam) -> dict:
    return _compute_scores_from_progress(
        template,
        team.item_progress or {},
        team.activity_progress or {},
        team.milestone_progress or {},
    )


# Fix typo: alias
def _calc_item_pts(item: dict, obtained: int) -> float:
    return _calc_item_points(item, obtained)


def _compute_scores_from_progress(
    template: FrenzyTemplate,
    item_progress: dict,
    activity_progress: dict,
    milestone_progress: dict,
) -> dict:
    multipliers: list = template.multipliers or []
    unlocked_mults = [m for m in multipliers if _is_multiplier_unlocked(m, item_progress)]
    unlocked_affects: dict[str, float] = {}
    for m in unlocked_mults:
        for src in m.get("affects", []):
            unlocked_affects[src] = unlocked_affects.get(src, 1.0) * m.get("factor", 1.0)

    tier_pts: dict[str, float] = {}
    for tier_name, tier_data in (template.tiers or {}).items():
        t_pts = 0.0
        for source in tier_data.get("sources", []):
            src_pts = 0.0
            src_name: str = source.get("name", "")
            for item in source.get("items", []):
                item_key = f"{tier_name}.{src_name}.{item.get('name', '')}"
                obtained = item_progress.get(item_key, 0)
                src_pts += _calc_item_pts(item, obtained)
            t_pts += src_pts * unlocked_affects.get(src_name, 1.0)
        tier_pts[tier_name] = t_pts

    activity_pts = sum(
        _calc_tier_entry_points(act, activity_progress.get(act.get("name", ""), 0))
        for act in (template.activities or [])
    )

    milestone_pts = 0.0
    for _cat, entries in (template.milestones or {}).items():
        for entry in entries:
            milestone_pts += _calc_tier_entry_points(
                entry, milestone_progress.get(entry.get("name", ""), 0)
            )

    return {
        "tier_points": tier_pts,
        "activity_points": activity_pts,
        "milestone_points": milestone_pts,
        "total": sum(tier_pts.values()) + activity_pts + milestone_pts,
    }


async def _recompute_team_progress(session: AsyncSession, team: FrenzyTeam) -> None:
    """Rebuild team JSONB caches from all approved submissions for this team."""
    submissions = (
        await session.execute(
            select(FrenzySubmission)
            .where(
                FrenzySubmission.team_id == team.id,
                FrenzySubmission.status == "approved",
            )
            .order_by(FrenzySubmission.submitted_at)
        )
    ).scalars().all()

    item_progress: dict[str, int] = {}
    # activity/milestone: {name: {discord_user_id: max_value}}
    activity_by_player: dict[str, dict[int, int]] = {}
    milestone_by_player: dict[str, dict[int, int]] = {}

    for sub in submissions:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_progress[key] = item_progress.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            activity_by_player.setdefault(name, {})
            activity_by_player[name][uid] = max(
                activity_by_player[name].get(uid, 0), p.get("value", 0)
            )
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            milestone_by_player.setdefault(name, {})
            milestone_by_player[name][uid] = max(
                milestone_by_player[name].get(uid, 0), p.get("value", 0)
            )

    team.item_progress = item_progress
    team.activity_progress = {n: sum(v.values()) for n, v in activity_by_player.items()}
    team.milestone_progress = {n: sum(v.values()) for n, v in milestone_by_player.items()}
    team.updated_at = datetime.now(timezone.utc)


def _apply_pending_submissions(
    base_item: dict,
    base_activity: dict,
    base_milestone: dict,
    pending: list[FrenzySubmission],
) -> tuple[dict, dict, dict]:
    """Merge pending submissions on top of approved state; returns new progress dicts."""
    item_p = dict(base_item)
    # For activities/milestones, track per-player maxes separately then sum
    act_by_player: dict[str, dict[int, int]] = {}
    mil_by_player: dict[str, dict[int, int]] = {}

    for sub in pending:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_p[key] = item_p.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_by_player.setdefault(name, {})
            act_by_player[name][uid] = max(act_by_player[name].get(uid, 0), p.get("value", 0))
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_by_player.setdefault(name, {})
            mil_by_player[name][uid] = max(mil_by_player[name].get(uid, 0), p.get("value", 0))

    act_p = dict(base_activity)
    for name, by_player in act_by_player.items():
        act_p[name] = act_p.get(name, 0) + sum(by_player.values())

    mil_p = dict(base_milestone)
    for name, by_player in mil_by_player.items():
        mil_p[name] = mil_p.get(name, 0) + sum(by_player.values())

    return item_p, act_p, mil_p


def _submission_to_dict(sub: FrenzySubmission, reviewer: User | None = None) -> dict:
    return {
        "id": sub.id,
        "event_id": sub.event_id,
        "team_id": sub.team_id,
        "discord_user_id": sub.discord_user_id,
        "player_rsn": sub.player_rsn,
        "source": sub.source,
        "submission_type": sub.submission_type,
        "payload": sub.payload,
        "status": sub.status,
        "auto_approved": sub.auto_approved,
        "reviewed_by": {
            "discord_user_id": reviewer.discord_user_id,
            "discord_username": reviewer.discord_username,
            "rsn": reviewer.rsn,
        } if reviewer else None,
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "review_notes": sub.review_notes,
        "submitted_at": sub.submitted_at.isoformat(),
        "created_at": sub.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# OSRS reference data
# ---------------------------------------------------------------------------

async def _refresh_osrs_items(valkey: Valkey) -> None:
    """Load all tradeable items from the GE prices API into Valkey."""
    async with httpx.AsyncClient(
        headers={"User-Agent": "The Iron Foundry Project / contact@ironfoundry.cc"},
        timeout=20.0,
    ) as client:
        resp = await client.get("https://prices.runescape.wiki/api/v1/osrs/mapping")
        resp.raise_for_status()
        raw = resp.json()
    items = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "icon_url": f"{_WIKI_IMAGE_BASE}/{entry['icon'].replace(' ', '_')}",
            "members": entry.get("members", False),
        }
        for entry in raw
        if entry.get("name") and entry.get("icon")
    ]
    await valkey.setex(_ITEMS_KEY, _OSRS_REF_TTL, json.dumps(items))
    logger.info("osrs items cache: loaded {} items", len(items))


async def _refresh_osrs_bosses(valkey: Valkey) -> None:
    bosses = [
        {
            "slug": slug,
            "name": name,
            "icon_url": _wiki_icon(icon_slug),
        }
        for slug, (name, icon_slug) in _BOSS_METRICS.items()
    ]
    await valkey.setex(_BOSSES_KEY, _OSRS_REF_TTL, json.dumps(bosses))
    logger.info("osrs bosses cache: loaded {} bosses", len(bosses))


async def _refresh_osrs_activities(valkey: Valkey) -> None:
    activities = [
        {
            "slug": slug,
            "name": name,
            "icon_url": _wiki_icon(icon_slug),
        }
        for slug, (name, icon_slug) in _ACTIVITY_METRICS.items()
    ]
    await valkey.setex(_ACTIVITIES_KEY, _OSRS_REF_TTL, json.dumps(activities))
    logger.info("osrs activities cache: loaded {} activities", len(activities))


async def warm_osrs_caches(valkey: Valkey) -> None:
    """Called from app lifespan to pre-populate OSRS reference data."""
    if not await valkey.exists(_ITEMS_KEY):
        await _refresh_osrs_items(valkey)
    if not await valkey.exists(_BOSSES_KEY):
        await _refresh_osrs_bosses(valkey)
    if not await valkey.exists(_ACTIVITIES_KEY):
        await _refresh_osrs_activities(valkey)


# ---------------------------------------------------------------------------
# Leaderboard cache
# ---------------------------------------------------------------------------

async def _build_lb_cache(valkey: Valkey, wom_comp_id: int | None, metrics: list[str]) -> None:
    acquired = await valkey.set(_LB_LOCK_KEY, "1", ex=_LB_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        out: list[dict] = []
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            timeout=15.0,
        ) as wom:
            for metric in metrics:
                entries = await wom.fetch_kc_metric(_WOM_GROUP_ID, metric)
                if entries:
                    boss_name, _ = _BOSS_METRICS.get(metric, (metric, metric))
                    out.append({"metric": metric, "display_name": boss_name, "entries": entries})

        if out:
            payload = json.dumps(out)
            await valkey.setex(_LB_FRESH_KEY, _LB_FRESH_TTL, payload)
            await valkey.setex(_LB_STALE_KEY, _LB_STALE_TTL, payload)
    finally:
        await valkey.delete(_LB_LOCK_KEY)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TemplateBody(BaseModel):
    name: str
    description: str | None = None
    tiers: dict = {}
    activities: list = []
    milestones: dict = {}
    multipliers: list = []


class EventBody(BaseModel):
    name: str
    template_id: int
    wom_comp_id: int | None = None
    leaderboard_metrics: list[str] = []
    trusted_sources: list[str] = []
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventPatch(BaseModel):
    name: str | None = None
    wom_comp_id: int | None = None
    leaderboard_metrics: list[str] | None = None
    trusted_sources: list[str] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


_VALID_SOURCES = {"trackscape", "discord_ocr", "discord_manual", "web"}
_VALID_SUBMISSION_TYPES = {"item", "activity", "milestone"}
_VALID_STATUSES = {"pending", "approved", "rejected"}


class SubmissionBody(BaseModel):
    discord_user_id: int
    player_rsn: str
    source: str
    submission_type: str
    payload: dict
    submitted_at: datetime | None = None


class SubmissionPatch(BaseModel):
    status: str
    review_notes: str | None = None


class TeamBody(BaseModel):
    name: str
    slug: str
    icon_url: str | None = None
    sort_order: int = 0


class TeamPatch(BaseModel):
    name: str | None = None
    icon_url: str | None = None
    sort_order: int | None = None
    item_progress: dict | None = None
    activity_progress: dict | None = None
    milestone_progress: dict | None = None


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.get("/active")
async def get_active_event(
    session: AsyncSession = Depends(get_session),
    _current_user: dict | None = Depends(get_optional_user),
) -> dict:
    """Return the active event with all teams ranked by total points."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(500, "Event template not found.")

    teams = (
        await session.execute(
            select(FrenzyTeam)
            .where(FrenzyTeam.event_id == event.id)
            .order_by(FrenzyTeam.sort_order)
        )
    ).scalars().all()

    # Load all pending submissions for this event in one query
    pending_by_team: dict[int, list[FrenzySubmission]] = {}
    pending_rows = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.event_id == event.id,
                FrenzySubmission.status == "pending",
            )
        )
    ).scalars().all()
    for sub in pending_rows:
        pending_by_team.setdefault(sub.team_id, []).append(sub)

    teams_out = []
    for team in teams:
        scores = _compute_team_scores(template, team)
        pending = pending_by_team.get(team.id, [])
        if pending:
            pi, pa, pm = _apply_pending_submissions(
                team.item_progress or {},
                team.activity_progress or {},
                team.milestone_progress or {},
                pending,
            )
            pending_scores = _compute_scores_from_progress(template, pi, pa, pm)
            pending_points = pending_scores["total"] - scores["total"]
        else:
            pending_points = 0.0

        teams_out.append(
            {
                "id": team.id,
                "name": team.name,
                "slug": team.slug,
                "icon_url": team.icon_url,
                "sort_order": team.sort_order,
                "total_points": scores["total"],
                "pending_points": pending_points,
                "tier_points": scores["tier_points"],
                "activity_points": scores["activity_points"],
                "milestone_points": scores["milestone_points"],
            }
        )

    teams_out.sort(key=lambda t: t["total_points"], reverse=True)

    return {
        "id": event.id,
        "name": event.name,
        "wom_comp_id": event.wom_comp_id,
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "template_id": event.template_id,
        "teams": teams_out,
    }


@router.get("/active/teams/{team_slug}")
async def get_active_team_detail(
    team_slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Full team detail: template merged with team progress and computed scores."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event.id,
                FrenzyTeam.slug == team_slug,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one()

    scores = _compute_team_scores(template, team)

    # Pending ghost score
    pending_subs = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.team_id == team.id,
                FrenzySubmission.status == "pending",
            )
        )
    ).scalars().all()

    if pending_subs:
        pi, pa, pm = _apply_pending_submissions(
            team.item_progress or {},
            team.activity_progress or {},
            team.milestone_progress or {},
            pending_subs,
        )
        pending_scores = _compute_scores_from_progress(template, pi, pa, pm)
        pending_points = pending_scores["total"] - scores["total"]
    else:
        pending_points = 0.0

    # Per-player contribution from approved submissions
    approved_subs = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.team_id == team.id,
                FrenzySubmission.status == "approved",
            )
        )
    ).scalars().all()

    player_contribution: dict[str, float] = {}
    for sub in approved_subs:
        p = sub.payload or {}
        pts = 0.0
        if sub.submission_type == "item":
            # Find the item definition in the template to compute points
            tier_name = p.get("tier", "")
            src_name = p.get("source_name", "")
            item_name = p.get("item_name", "")
            tier_data = (template.tiers or {}).get(tier_name, {})
            for source in tier_data.get("sources", []):
                if source.get("name") == src_name:
                    for item in source.get("items", []):
                        if item.get("name") == item_name:
                            pts = _calc_item_pts(item, p.get("quantity", 1))
                            break
        # Activities/milestones contribution is approximate (point delta per submission)
        # - not computed here since absolute values make per-sub attribution ambiguous
        rsn = sub.player_rsn
        player_contribution[rsn] = player_contribution.get(rsn, 0.0) + pts

    return {
        "id": team.id,
        "name": team.name,
        "slug": team.slug,
        "icon_url": team.icon_url,
        "participants": team.participants or [],
        "template": {
            "tiers": template.tiers,
            "activities": template.activities,
            "milestones": template.milestones,
            "multipliers": template.multipliers,
        },
        "progress": {
            "item_progress": team.item_progress,
            "activity_progress": team.activity_progress,
            "milestone_progress": team.milestone_progress,
        },
        "scores": scores,
        "pending_points": pending_points,
        "player_contribution": player_contribution,
    }


@router.get("/leaderboards")
async def get_leaderboards(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Leaderboard data with Valkey stale-while-revalidate."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()

    metrics: list[str] = []
    wom_comp_id: int | None = None
    if event:
        metrics = event.leaderboard_metrics or []
        wom_comp_id = event.wom_comp_id

    fresh = await valkey.get(_LB_FRESH_KEY)
    if fresh:
        return {"data": json.loads(fresh), "pending_metrics": []}

    stale = await valkey.get(_LB_STALE_KEY)
    if stale:
        background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)
        return {"data": json.loads(stale), "pending_metrics": [], "stale": True}

    if metrics:
        background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)

    return {
        "data": [],
        "pending_metrics": metrics,
        "stale": False,
    }


@router.get("/active/teams/{team_slug}/history")
async def get_team_history(
    team_slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Time-series of cumulative approved points for a team, plus per-player contribution."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event.id,
                FrenzyTeam.slug == team_slug,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one()

    approved_subs = (
        await session.execute(
            select(FrenzySubmission)
            .where(
                FrenzySubmission.team_id == team.id,
                FrenzySubmission.status == "approved",
            )
            .order_by(FrenzySubmission.submitted_at)
        )
    ).scalars().all()

    # Build cumulative score at each submission point
    item_p: dict[str, int] = {}
    act_by_player: dict[str, dict[int, int]] = {}
    mil_by_player: dict[str, dict[int, int]] = {}
    points_series: list[dict] = []
    player_contribution: dict[str, float] = {}

    for sub in approved_subs:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_p[key] = item_p.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_by_player.setdefault(name, {})
            act_by_player[name][uid] = max(act_by_player[name].get(uid, 0), p.get("value", 0))
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_by_player.setdefault(name, {})
            mil_by_player[name][uid] = max(mil_by_player[name].get(uid, 0), p.get("value", 0))

        act_p = {n: sum(v.values()) for n, v in act_by_player.items()}
        mil_p = {n: sum(v.values()) for n, v in mil_by_player.items()}
        scores = _compute_scores_from_progress(template, item_p, act_p, mil_p)

        if sub.submission_type == "item":
            tier_name = p.get("tier", "")
            src_name = p.get("source_name", "")
            item_name = p.get("item_name", "")
            tier_data = (template.tiers or {}).get(tier_name, {})
            item_pts = 0.0
            for source in tier_data.get("sources", []):
                if source.get("name") == src_name:
                    for item in source.get("items", []):
                        if item.get("name") == item_name:
                            item_pts = _calc_item_pts(item, p.get("quantity", 1))
                            break
            player_contribution[sub.player_rsn] = (
                player_contribution.get(sub.player_rsn, 0.0) + item_pts
            )

        points_series.append(
            {
                "timestamp": sub.submitted_at.isoformat(),
                "total_points": scores["total"],
                "player_rsn": sub.player_rsn,
                "submission_type": sub.submission_type,
                "payload": sub.payload,
            }
        )

    return {
        "team_slug": team_slug,
        "series": points_series,
        "player_contribution": player_contribution,
    }


@router.get("/active/history")
async def get_event_history(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """All teams' cumulative points over time - used for rank-over-time chart."""
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")

    teams = (
        await session.execute(
            select(FrenzyTeam).where(FrenzyTeam.event_id == event.id)
        )
    ).scalars().all()

    template = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == event.template_id)
        )
    ).scalar_one()

    all_subs = (
        await session.execute(
            select(FrenzySubmission)
            .where(
                FrenzySubmission.event_id == event.id,
                FrenzySubmission.status == "approved",
            )
            .order_by(FrenzySubmission.submitted_at)
        )
    ).scalars().all()

    # Per-team incremental state
    item_states: dict[int, dict[str, int]] = {t.id: {} for t in teams}
    act_states: dict[int, dict[str, dict[int, int]]] = {t.id: {} for t in teams}
    mil_states: dict[int, dict[str, dict[int, int]]] = {t.id: {} for t in teams}
    current_scores: dict[int, float] = {t.id: 0.0 for t in teams}

    team_series: dict[int, list[dict]] = {t.id: [] for t in teams}

    for sub in all_subs:
        tid = sub.team_id
        p = sub.payload or {}

        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_states[tid][key] = item_states[tid].get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_states[tid].setdefault(name, {})
            act_states[tid][name][uid] = max(act_states[tid][name].get(uid, 0), p.get("value", 0))
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_states[tid].setdefault(name, {})
            mil_states[tid][name][uid] = max(mil_states[tid][name].get(uid, 0), p.get("value", 0))

        act_p = {n: sum(v.values()) for n, v in act_states[tid].items()}
        mil_p = {n: sum(v.values()) for n, v in mil_states[tid].items()}
        scores = _compute_scores_from_progress(template, item_states[tid], act_p, mil_p)
        current_scores[tid] = scores["total"]

        team_series[tid].append(
            {
                "timestamp": sub.submitted_at.isoformat(),
                "total_points": scores["total"],
            }
        )

    return {
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "series": team_series[t.id],
            }
            for t in teams
        ]
    }


# ---------------------------------------------------------------------------
# OSRS reference data endpoints
# ---------------------------------------------------------------------------

@router.get("/osrs/items")
async def search_osrs_items(
    q: str = Query("", min_length=0),
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    if not q or len(q) < 2:
        return []
    raw = await valkey.get(_ITEMS_KEY)
    if not raw:
        try:
            await _refresh_osrs_items(valkey)
            raw = await valkey.get(_ITEMS_KEY)
        except Exception as exc:
            logger.warning("osrs items refresh failed: {}", exc)
            return []
    if not raw:
        return []
    norm_q = q.lower().replace("'", "").strip()
    all_items: list[dict] = json.loads(raw)
    results = [
        item for item in all_items
        if norm_q in item["name"].lower().replace("'", "")
    ]
    return results[:30]


@router.get("/osrs/bosses")
async def get_osrs_bosses(valkey: Valkey = Depends(get_valkey)) -> list[dict]:
    raw = await valkey.get(_BOSSES_KEY)
    if not raw:
        await _refresh_osrs_bosses(valkey)
        raw = await valkey.get(_BOSSES_KEY)
    return json.loads(raw) if raw else []


@router.get("/osrs/activities")
async def get_osrs_activities(valkey: Valkey = Depends(get_valkey)) -> list[dict]:
    raw = await valkey.get(_ACTIVITIES_KEY)
    if not raw:
        await _refresh_osrs_activities(valkey)
        raw = await valkey.get(_ACTIVITIES_KEY)
    return json.loads(raw) if raw else []


# ---------------------------------------------------------------------------
# Admin - Templates
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates(
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> list[dict]:
    rows = (
        await session.execute(
            select(FrenzyTemplate).order_by(FrenzyTemplate.updated_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "version_number": t.version_number,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in rows
    ]


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    now = datetime.now(timezone.utc)
    uid = int(current_user["sub"])
    tmpl = FrenzyTemplate(
        name=body.name,
        description=body.description,
        tiers=body.tiers,
        activities=body.activities,
        milestones=body.milestones,
        multipliers=body.multipliers,
        version_number=1,
        created_by=uid,
        created_at=now,
        updated_at=now,
    )
    session.add(tmpl)
    await session.flush()

    # Create initial version snapshot
    version = FrenzyTemplateVersion(
        template_id=tmpl.id,
        version_number=1,
        tiers=body.tiers,
        activities=body.activities,
        milestones=body.milestones,
        multipliers=body.multipliers,
        edited_by=uid,
        created_at=now,
    )
    session.add(version)
    await session.commit()

    return {"id": tmpl.id, "version_number": 1}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "description": tmpl.description,
        "tiers": tmpl.tiers,
        "activities": tmpl.activities,
        "milestones": tmpl.milestones,
        "multipliers": tmpl.multipliers,
        "version_number": tmpl.version_number,
        "created_at": tmpl.created_at.isoformat(),
        "updated_at": tmpl.updated_at.isoformat(),
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    body: TemplateBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    # Snapshot current state before overwriting
    max_ver_result = await session.execute(
        select(func.max(FrenzyTemplateVersion.version_number)).where(
            FrenzyTemplateVersion.template_id == template_id
        )
    )
    max_ver = max_ver_result.scalar_one_or_none()
    next_ver = (max_ver or 0) + 1

    version = FrenzyTemplateVersion(
        template_id=tmpl.id,
        version_number=next_ver,
        tiers=tmpl.tiers,
        activities=tmpl.activities,
        milestones=tmpl.milestones,
        multipliers=tmpl.multipliers,
        edited_by=uid,
        created_at=now,
    )
    session.add(version)

    tmpl.name = body.name
    tmpl.description = body.description
    tmpl.tiers = body.tiers
    tmpl.activities = body.activities
    tmpl.milestones = body.milestones
    tmpl.multipliers = body.multipliers
    tmpl.version_number = next_ver
    tmpl.updated_at = now

    await session.commit()
    return {"id": tmpl.id, "version_number": tmpl.version_number, "updated_at": now.isoformat()}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    # Prevent deletion if any event references this template
    event_count = (
        await session.execute(
            select(func.count(FrenzyEvent.id)).where(FrenzyEvent.template_id == template_id)
        )
    ).scalar_one()
    if event_count > 0:
        raise HTTPException(409, "Template is referenced by one or more events.")

    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    await session.delete(tmpl)
    await session.commit()
    return {"ok": True}


@router.get("/templates/{template_id}/versions")
async def list_template_versions(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> list[dict]:
    result = await session.execute(
        select(FrenzyTemplateVersion, User)
        .join(User, User.discord_user_id == FrenzyTemplateVersion.edited_by, isouter=True)
        .where(FrenzyTemplateVersion.template_id == template_id)
        .order_by(FrenzyTemplateVersion.version_number.desc())
    )
    rows = result.all()
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "created_at": v.created_at.isoformat(),
            "edited_by": {
                "discord_user_id": u.discord_user_id,
                "discord_username": u.discord_username,
                "rsn": u.rsn,
                "avatar": u.discord_avatar_url,
            }
            if u
            else None,
        }
        for v, u in rows
    ]


@router.get("/templates/{template_id}/versions/{version_id}")
async def get_template_version(
    template_id: int,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    result = await session.execute(
        select(FrenzyTemplateVersion, User)
        .join(User, User.discord_user_id == FrenzyTemplateVersion.edited_by, isouter=True)
        .where(
            FrenzyTemplateVersion.id == version_id,
            FrenzyTemplateVersion.template_id == template_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Version not found.")
    v, u = row
    return {
        "id": v.id,
        "version_number": v.version_number,
        "tiers": v.tiers,
        "activities": v.activities,
        "milestones": v.milestones,
        "multipliers": v.multipliers,
        "created_at": v.created_at.isoformat(),
        "edited_by": {
            "discord_user_id": u.discord_user_id,
            "discord_username": u.discord_username,
            "rsn": u.rsn,
            "avatar": u.discord_avatar_url,
        }
        if u
        else None,
    }


@router.post("/templates/{template_id}/revert/{version_id}")
async def revert_template_to_version(
    template_id: int,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    ver = (
        await session.execute(
            select(FrenzyTemplateVersion).where(
                FrenzyTemplateVersion.id == version_id,
                FrenzyTemplateVersion.template_id == template_id,
            )
        )
    ).scalar_one_or_none()
    if ver is None:
        raise HTTPException(404, "Version not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    # Snapshot current state before reverting
    max_ver_result = await session.execute(
        select(func.max(FrenzyTemplateVersion.version_number)).where(
            FrenzyTemplateVersion.template_id == template_id
        )
    )
    max_ver = max_ver_result.scalar_one_or_none()
    next_ver = (max_ver or 0) + 1

    snapshot = FrenzyTemplateVersion(
        template_id=tmpl.id,
        version_number=next_ver,
        tiers=tmpl.tiers,
        activities=tmpl.activities,
        milestones=tmpl.milestones,
        multipliers=tmpl.multipliers,
        edited_by=uid,
        created_at=now,
    )
    session.add(snapshot)

    tmpl.tiers = ver.tiers
    tmpl.activities = ver.activities
    tmpl.milestones = ver.milestones
    tmpl.multipliers = ver.multipliers
    tmpl.version_number = next_ver
    tmpl.updated_at = now

    await session.commit()
    return {"id": tmpl.id, "version_number": tmpl.version_number, "updated_at": now.isoformat()}


# ---------------------------------------------------------------------------
# Admin - Events
# ---------------------------------------------------------------------------

@router.get("/events")
async def list_events(
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> list[dict]:
    rows = (
        await session.execute(
            select(FrenzyEvent).order_by(FrenzyEvent.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "template_id": e.template_id,
            "wom_comp_id": e.wom_comp_id,
            "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            "ends_at": e.ends_at.isoformat() if e.ends_at else None,
            "is_active": e.is_active,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]


@router.post("/events", status_code=201)
async def create_event(
    body: EventBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    # Verify template exists
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == body.template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    now = datetime.now(timezone.utc)
    uid = int(current_user["sub"])
    event = FrenzyEvent(
        name=body.name,
        template_id=body.template_id,
        wom_comp_id=body.wom_comp_id,
        leaderboard_metrics=body.leaderboard_metrics,
        trusted_sources=body.trusted_sources,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=False,
        created_by=uid,
        created_at=now,
        updated_at=now,
    )
    session.add(event)
    await session.commit()
    return {"id": event.id}


@router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    teams = (
        await session.execute(
            select(FrenzyTeam)
            .where(FrenzyTeam.event_id == event_id)
            .order_by(FrenzyTeam.sort_order)
        )
    ).scalars().all()

    return {
        "id": event.id,
        "name": event.name,
        "template_id": event.template_id,
        "wom_comp_id": event.wom_comp_id,
        "leaderboard_metrics": event.leaderboard_metrics,
        "trusted_sources": event.trusted_sources or [],
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "is_active": event.is_active,
        "created_at": event.created_at.isoformat(),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "icon_url": t.icon_url,
                "sort_order": t.sort_order,
                "participants": t.participants or [],
            }
            for t in teams
        ],
    }


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    body: EventPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    now = datetime.now(timezone.utc)
    if body.name is not None:
        event.name = body.name
    if body.wom_comp_id is not None:
        event.wom_comp_id = body.wom_comp_id
    if body.leaderboard_metrics is not None:
        event.leaderboard_metrics = body.leaderboard_metrics
    if body.trusted_sources is not None:
        event.trusted_sources = body.trusted_sources
    if body.starts_at is not None:
        event.starts_at = body.starts_at
    if body.ends_at is not None:
        event.ends_at = body.ends_at
    event.updated_at = now

    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.delete(event)
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/activate")
async def activate_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    # Deactivate all other events first
    await session.execute(
        update(FrenzyEvent)
        .where(FrenzyEvent.id != event_id)
        .values(is_active=False)
    )
    event.is_active = True
    await session.commit()
    return {"ok": True, "active_event_id": event_id}


@router.post("/events/{event_id}/deactivate")
async def deactivate_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.is_active = False
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin - Teams
# ---------------------------------------------------------------------------

@router.post("/events/{event_id}/teams", status_code=201)
async def add_team(
    event_id: int,
    body: TeamBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    existing = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id,
                FrenzyTeam.slug == body.slug,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"Team with slug '{body.slug}' already exists in this event.")

    now = datetime.now(timezone.utc)
    team = FrenzyTeam(
        event_id=event_id,
        name=body.name,
        slug=body.slug,
        icon_url=body.icon_url,
        sort_order=body.sort_order,
        participants=[],
        item_progress={},
        activity_progress={},
        milestone_progress={},
        updated_at=now,
    )
    session.add(team)
    await session.commit()
    return {"id": team.id, "slug": team.slug}


@router.patch("/events/{event_id}/teams/{team_slug}")
async def patch_team(
    event_id: int,
    team_slug: str,
    body: TeamPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id,
                FrenzyTeam.slug == team_slug,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")

    if body.name is not None:
        team.name = body.name
    if body.icon_url is not None:
        team.icon_url = body.icon_url
    if body.sort_order is not None:
        team.sort_order = body.sort_order
    if body.item_progress is not None:
        team.item_progress = body.item_progress
    if body.activity_progress is not None:
        team.activity_progress = body.activity_progress
    if body.milestone_progress is not None:
        team.milestone_progress = body.milestone_progress
    team.updated_at = datetime.now(timezone.utc)

    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}/teams/{team_slug}")
async def delete_team(
    event_id: int,
    team_slug: str,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id,
                FrenzyTeam.slug == team_slug,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")
    await session.delete(team)
    await session.commit()
    return {"ok": True}


def _slugify(name: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


@router.post("/events/{event_id}/sync-wom")
async def sync_event_from_wom(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    """Pull teams, participants, and dates from the linked WOM competition."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    if not event.wom_comp_id:
        raise HTTPException(400, "Event has no WOM competition ID set.")

    async with WiseOldManHandler(
        api_key=_WOM_API_KEY,
        discord_contact=_WOM_DISCORD_CONTACT,
        timeout=15.0,
    ) as wom:
        comp = await wom.get_competition_details(event.wom_comp_id)

    now = datetime.now(timezone.utc)

    # Sync dates
    if comp.get("startsAt"):
        event.starts_at = datetime.fromisoformat(comp["startsAt"].replace("Z", "+00:00"))
    if comp.get("endsAt"):
        event.ends_at = datetime.fromisoformat(comp["endsAt"].replace("Z", "+00:00"))
    event.updated_at = now

    synced_teams: list[dict] = []

    if comp.get("type") == "team":
        # WOM returns a flat `participations` list; each entry has `teamName` and `player`.
        teams_map: dict[str, list[str]] = {}
        for p in comp.get("participations", []):
            t_name = p.get("teamName", "")
            rsn = (p.get("player") or {}).get("displayName", "")
            if t_name and rsn:
                teams_map.setdefault(t_name, []).append(rsn)

        existing_teams = (
            await session.execute(
                select(FrenzyTeam).where(FrenzyTeam.event_id == event_id)
            )
        ).scalars().all()
        teams_by_slug = {t.slug: t for t in existing_teams}

        for i, (team_name, participants) in enumerate(teams_map.items()):
            slug = _slugify(team_name)

            if slug in teams_by_slug:
                team = teams_by_slug[slug]
                team.participants = participants
                team.updated_at = now
            else:
                team = FrenzyTeam(
                    event_id=event_id,
                    name=team_name,
                    slug=slug,
                    icon_url=None,
                    sort_order=i,
                    participants=participants,
                    item_progress={},
                    activity_progress={},
                    milestone_progress={},
                    updated_at=now,
                )
                session.add(team)

            synced_teams.append({"name": team_name, "slug": slug, "participants": participants})

    await session.commit()

    return {
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "teams_synced": len(synced_teams),
        "teams": synced_teams,
    }


@router.post("/leaderboards/refresh")
async def refresh_leaderboards(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    await valkey.delete(_LB_FRESH_KEY)

    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()

    metrics: list[str] = event.leaderboard_metrics if event else []
    wom_comp_id: int | None = event.wom_comp_id if event else None

    background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin - Submissions
# ---------------------------------------------------------------------------

@router.get("/events/{event_id}/submissions")
async def list_submissions(
    event_id: int,
    team_id: int | None = Query(None),
    status: str | None = Query(None),
    submission_type: str | None = Query(None),
    source: str | None = Query(None),
    player_rsn: str | None = Query(None),
    auto_approved: bool | None = Query(None),
    submitted_after: datetime | None = Query(None),
    submitted_before: datetime | None = Query(None),
    q: str | None = Query(None, min_length=1),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    stmt = select(FrenzySubmission).where(FrenzySubmission.event_id == event_id)
    if team_id is not None:
        stmt = stmt.where(FrenzySubmission.team_id == team_id)
    if status is not None:
        if status not in _VALID_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of: {_VALID_STATUSES}")
        stmt = stmt.where(FrenzySubmission.status == status)
    if submission_type is not None:
        if submission_type not in _VALID_SUBMISSION_TYPES:
            raise HTTPException(400, "Invalid submission_type.")
        stmt = stmt.where(FrenzySubmission.submission_type == submission_type)
    if source is not None:
        if source not in _VALID_SOURCES:
            raise HTTPException(400, f"Invalid source. Must be one of: {_VALID_SOURCES}")
        stmt = stmt.where(FrenzySubmission.source == source)
    if player_rsn is not None:
        stmt = stmt.where(FrenzySubmission.player_rsn.ilike(f"%{player_rsn}%"))
    if auto_approved is not None:
        stmt = stmt.where(FrenzySubmission.auto_approved == auto_approved)
    if submitted_after is not None:
        stmt = stmt.where(FrenzySubmission.submitted_at >= submitted_after)
    if submitted_before is not None:
        stmt = stmt.where(FrenzySubmission.submitted_at <= submitted_before)
    if q is not None:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                FrenzySubmission.player_rsn.ilike(like),
                FrenzySubmission.payload["item_name"].astext.ilike(like),
                FrenzySubmission.payload["source_name"].astext.ilike(like),
                FrenzySubmission.payload["name"].astext.ilike(like),
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(FrenzySubmission.submitted_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    reviewer_ids = {s.reviewed_by for s in rows if s.reviewed_by}
    reviewers: dict[int, User] = {}
    if reviewer_ids:
        reviewer_rows = (
            await session.execute(
                select(User).where(User.discord_user_id.in_(reviewer_ids))
            )
        ).scalars().all()
        reviewers = {u.discord_user_id: u for u in reviewer_rows}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "submissions": [_submission_to_dict(s, reviewers.get(s.reviewed_by)) for s in rows],
    }


@router.post("/events/{event_id}/submissions", status_code=201)
async def create_submission(
    event_id: int,
    body: SubmissionBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if body.source not in _VALID_SOURCES:
        raise HTTPException(400, f"Invalid source. Must be one of: {_VALID_SOURCES}")
    if body.submission_type not in _VALID_SUBMISSION_TYPES:
        raise HTTPException(400, "Invalid submission_type.")

    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    # team_id must come from the payload
    team_id: int | None = body.payload.get("team_id")
    if team_id is None:
        raise HTTPException(400, "payload must include team_id.")
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.id == team_id,
                FrenzyTeam.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found in this event.")

    trusted: list[str] = event.trusted_sources or []
    auto_approve = body.source in trusted
    now = datetime.now(timezone.utc)
    submitted_at = body.submitted_at or now

    sub = FrenzySubmission(
        event_id=event_id,
        team_id=team.id,
        discord_user_id=body.discord_user_id,
        player_rsn=body.player_rsn,
        source=body.source,
        submission_type=body.submission_type,
        payload={k: v for k, v in body.payload.items() if k != "team_id"},
        status="approved" if auto_approve else "pending",
        auto_approved=auto_approve,
        reviewed_by=int(current_user["sub"]) if auto_approve else None,
        reviewed_at=now if auto_approve else None,
        submitted_at=submitted_at,
        created_at=now,
    )
    session.add(sub)
    await session.flush()

    if auto_approve:
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"id": sub.id, "status": sub.status, "auto_approved": sub.auto_approved}


@router.patch("/events/{event_id}/submissions/{submission_id}")
async def patch_submission(
    event_id: int,
    submission_id: int,
    body: SubmissionPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {_VALID_STATUSES}")

    sub = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.id == submission_id,
                FrenzySubmission.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Submission not found.")

    prev_status = sub.status
    sub.status = body.status
    sub.review_notes = body.review_notes
    sub.reviewed_by = int(current_user["sub"])
    sub.reviewed_at = datetime.now(timezone.utc)

    if body.status != prev_status and body.status in ("approved", "rejected"):
        team = (
            await session.execute(
                select(FrenzyTeam).where(FrenzyTeam.id == sub.team_id)
            )
        ).scalar_one()
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"ok": True, "status": sub.status}


@router.delete("/events/{event_id}/submissions/{submission_id}")
async def delete_submission(
    event_id: int,
    submission_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = Depends(require_page_permission("frenzy", "edit")),
) -> dict:
    sub = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.id == submission_id,
                FrenzySubmission.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Submission not found.")

    was_approved = sub.status == "approved"
    team_id = sub.team_id

    await session.delete(sub)
    await session.flush()

    if was_approved:
        team = (
            await session.execute(select(FrenzyTeam).where(FrenzyTeam.id == team_id))
        ).scalar_one()
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"ok": True}
