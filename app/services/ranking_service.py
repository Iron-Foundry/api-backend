"""Daily background service that fetches WOM player snapshots and ranks the clan."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Config, PlayerRanking, PlayerSnapshot, UserAccount
from app.services.http.wom import WiseOldManHandler

POLL_INTERVAL = 86400  # 24 hours

_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")

_GLOBAL_GUILD_ID = 0
_RANKING_CONFIG_KEY = "ranking_config"

_DEFAULT_CONFIG: dict[str, Any] = {
    "multipliers": {"boss": 2.0, "skill": 1.0},
    "thresholds": {
        "rank_1": 0,
        "rank_2": 10000,
        "rank_3": 20000,
        "rank_4": 30000,
        "rank_5": 45000,
        "rank_6": 60000,
    },
    "boss_tier_multipliers": {
        "tier_1": 1,
        "tier_2": 2,
        "tier_3": 3,
        "tier_4": 4,
        "tier_5": 5,
        "toa": 3,
        "tob": 5,
        "cox": 4,
    },
    "skill_exp_tiers": {
        "tier_1": 0,
        "tier_2": 101334,
        "tier_3": 737628,
        "tier_4": 1986069,
        "tier_5": 5346333,
        "max": 13034431,
    },
    "skills": [
        "attack",
        "strength",
        "defense",
        "range",
        "magic",
        "prayer",
        "hitpoints",
        "slayer",
        "cooking",
        "woodcutting",
        "fletching",
        "fishing",
        "firemaking",
        "crafting",
        "smithing",
        "mining",
        "herblore",
        "agility",
        "thieving",
        "farming",
        "runecrafting",
        "hunter",
        "construction",
        "sailing",
    ],
    "kc_tiers": {
        "tier_1": 0,
        "tier_2": 50,
        "tier_3": 100,
        "tier_4": 250,
        "tier_5": 750,
    },
    "tier_1_bosses": [
        "barrows_chests",
        "scurrius",
        "giant_mole",
        "deranged_archaeologist",
        "chaos_fanatic",
        "crazy_archaeologist",
        "obor",
        "bryophyta",
        "amoxliatl",
        "hespori",
        "kraken",
        "shellbane_gryphon",
        "thermonuclear_smoke_devil",
    ],
    "tier_2_bosses": [
        "dagannoth_prime",
        "dagannoth_rex",
        "dagannoth_supreme",
        "scorpia",
        "king_black_dragon",
        "grotesque_guardians",
        "calvarion",
        "sarachnis",
        "the_hueycoatl",
        "lunar_chests",
        "chaos_elemental",
        "mimic",
        "vetion",
        "spindel",
        "venenatis",
        "artio",
        "callisto",
        "the_royal_titans",
        "skotizo",
        "abyssal_sire",
        "cerberus",
        "alchemical_hydra",
        "kril_tsutsaroth",
        "duke_sucellus",
        "tztok_jad",
    ],
    "tier_3_bosses": [
        "general_graardor",
        "kreearra",
        "kalphite_queen",
        "commander_zilyana",
        "corporeal_beast",
        "zulrah",
        "vorkath",
        "phantom_muspah",
        "araxxor",
        "the_gauntlet",
    ],
    "tier_4_bosses": [
        "nex",
        "yama",
        "nightmare",
        "the_leviathan",
        "the_whisperer",
        "vardorvis",
        "the_corrupted_gauntlet",
    ],
    "tier_5_bosses": [
        "tzkal_zuk",
        "sol_heredit",
        "phosanis_nightmare",
        "doom_of_mokhaiotl",
    ],
    "raids": {
        "toa": ["tombs_of_amascut", "tombs_of_amascut_expert"],
        "tob": ["theatre_of_blood", "theatre_of_blood_hard_mode"],
        "cox": ["chambers_of_xeric", "chambers_of_xeric_challenge_mode"],
    },
}


# ── Algorithm helpers ─────────────────────────────────────────────────────────


def _boss_score(kc: int, tiers: dict) -> int:
    if kc >= tiers["tier_5"]:
        return 5
    if kc >= tiers["tier_4"]:
        return 4
    if kc >= tiers["tier_3"]:
        return 3
    if kc >= tiers["tier_2"]:
        return 2
    if kc > tiers["tier_1"]:
        return 1
    return 0


def _tier_avg(boss_kcs: dict[str, int], kc_tiers: dict, multiplier: float) -> float:
    if not boss_kcs:
        return 0.0
    total = sum(_boss_score(kc, kc_tiers) * multiplier for kc in boss_kcs.values())
    return total / len(boss_kcs)


def _skill_score(exp: float, tiers: dict) -> int:
    if exp >= tiers["max"]:
        return 5
    if exp >= tiers["tier_5"]:
        return 4
    if exp >= tiers["tier_4"]:
        return 3
    if exp >= tiers["tier_3"]:
        return 2
    if exp > tiers["tier_1"]:
        return 1
    return 0


def _assign_rank(points: int, thresholds: dict) -> str:
    if points >= thresholds["rank_6"]:
        return "Rank 6"
    if points >= thresholds["rank_5"]:
        return "Rank 5"
    if points >= thresholds["rank_4"]:
        return "Rank 4"
    if points >= thresholds["rank_3"]:
        return "Rank 3"
    if points >= thresholds["rank_2"]:
        return "Rank 2"
    if points > thresholds["rank_1"]:
        return "Rank 1"
    return "No Rank"


_RANK_ORDER = {
    "No Rank": 0,
    "Rank 1": 1,
    "Rank 2": 2,
    "Rank 3": 3,
    "Rank 4": 4,
    "Rank 5": 5,
    "Rank 6": 6,
}


def rank_from_snapshots(
    snapshots: list[dict],  # list of {rsn, skills, bosses}
    config: dict,
) -> list[dict]:
    """Pure ranking computation - no DB access.

    Returns list of {rsn, rank, points, boss_points, skill_points}.
    """
    mults = config["multipliers"]
    thresholds = config["thresholds"]
    kc_tiers = config["kc_tiers"]
    exp_tiers = config["skill_exp_tiers"]
    skill_names = set(config["skills"])
    tier_mults = config["boss_tier_multipliers"]

    tier_boss_lists = {
        "t1": config["tier_1_bosses"],
        "t2": config["tier_2_bosses"],
        "t3": config["tier_3_bosses"],
        "t4": config["tier_4_bosses"],
        "t5": config["tier_5_bosses"],
    }
    raid_lists = config["raids"]

    results = []
    for snap in snapshots:
        rsn = snap["rsn"]
        skills = snap["skills"]
        bosses = snap["bosses"]

        # Boss score
        boss_raw = 0.0
        for tier_key, boss_names in tier_boss_lists.items():
            mult_key = f"tier_{tier_key[1]}"
            kcs = {b: bosses[b] for b in boss_names if b in bosses}
            boss_raw += _tier_avg(kcs, kc_tiers, tier_mults[mult_key])
        for raid_key, raid_names in raid_lists.items():
            kcs = {b: bosses[b] for b in raid_names if b in bosses}
            boss_raw += _tier_avg(kcs, kc_tiers, tier_mults[raid_key])

        # Skill score
        tracked = {s: float(v) for s, v in skills.items() if s in skill_names}
        if tracked:
            skill_raw = sum(
                _skill_score(exp, exp_tiers) for exp in tracked.values()
            ) / len(tracked)
        else:
            skill_raw = 0.0

        raw = (boss_raw * mults["boss"] + skill_raw * mults["skill"]) / 2
        points = int(raw * 1000)
        boss_points = int(boss_raw * mults["boss"] * 1000 / 2)
        skill_points = int(skill_raw * mults["skill"] * 1000 / 2)

        results.append(
            {
                "rsn": rsn,
                "rank": _assign_rank(points, thresholds),
                "points": points,
                "boss_points": boss_points,
                "skill_points": skill_points,
            }
        )

    results.sort(key=lambda p: (-_RANK_ORDER.get(p["rank"], 0), -p["points"]))
    return results


# ── Service ───────────────────────────────────────────────────────────────────


class RankingService:
    """Fetches WOM player snapshots and ranks the clan once per day."""

    def __init__(
        self, session_factory, group_id: int, api_key: str | None = None
    ) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._group_id = group_id
        self._api_key = api_key
        self._task: asyncio.Task[None] | None = None
        self._run_event = asyncio.Event()
        self.is_running: bool = False
        self.last_run_at: datetime | None = None
        self.last_run_count: int = 0
        self.last_error: str | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="ranking-service")
        logger.info(
            "RankingService started (group_id={}, poll_interval={}s)",
            self._group_id,
            POLL_INTERVAL,
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RankingService stopped")

    def run_now(self) -> bool:
        """Trigger an immediate ranking run. Returns False if already running."""
        if self.is_running:
            return False
        self._run_event.set()
        return True

    async def _poll_loop(self) -> None:
        while True:
            self._run_event.clear()
            self.is_running = True
            try:
                await self._refresh()
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("RankingService._refresh error: {}", exc)
            finally:
                self.is_running = False
            try:
                await asyncio.wait_for(self._run_event.wait(), timeout=POLL_INTERVAL)
            except TimeoutError:
                pass

    async def _get_config(self) -> dict:
        if self._session_factory is None:
            return _DEFAULT_CONFIG
        async with self._session_factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GLOBAL_GUILD_ID,
                    Config.key == _RANKING_CONFIG_KEY,
                )
            )
            stored = result.scalar_one_or_none()
        if not stored:
            return _DEFAULT_CONFIG
        merged = dict(_DEFAULT_CONFIG)
        merged.update(stored)
        return merged

    async def _refresh(self) -> None:
        if self._session_factory is None:
            logger.warning("RankingService: no session_factory - skipping")
            return

        config = await self._get_config()
        logger.info("RankingService: fetching group {} from WOM", self._group_id)

        async with WiseOldManHandler(
            api_key=self._api_key, discord_contact=_WOM_DISCORD_CONTACT
        ) as wom:
            group_data = await wom.get_group(self._group_id)
            memberships = group_data.get("memberships", [])
            usernames = [m["player"]["username"] for m in memberships]

            logger.info("RankingService: fetching {} player snapshots", len(usernames))
            snapshots_raw: list[tuple[str, dict]] = []
            for username in usernames:
                try:
                    details = await wom.get_player_details(username)
                    if details:
                        snapshots_raw.append((username, details))
                except Exception as exc:
                    logger.warning(
                        "RankingService: failed to fetch {}: {}", username, exc
                    )

        logger.info(
            "RankingService: fetched {}/{} snapshots",
            len(snapshots_raw),
            len(usernames),
        )

        now = datetime.now(timezone.utc)
        cleaned: list[dict] = []
        snapshot_rows = []

        skill_names = set(config["skills"])
        for username, details in snapshots_raw:
            rsn = username.lower()
            snapshot = details.get("latestSnapshot", {})
            if not snapshot:
                continue
            data = snapshot.get("data", {})
            skills_data = data.get("skills", {})
            bosses_data = data.get("bosses", {})

            skills = {
                name: float(
                    info.get("experience", 0) if isinstance(info, dict) else info
                )
                for name, info in skills_data.items()
                if name in skill_names
            }
            bosses = {
                name: int(info.get("kills", 0) if isinstance(info, dict) else info)
                for name, info in bosses_data.items()
            }

            cleaned.append({"rsn": rsn, "skills": skills, "bosses": bosses})
            snapshot_rows.append(
                {"rsn": rsn, "skills": skills, "bosses": bosses, "fetched_at": now}
            )

        ranked = rank_from_snapshots(cleaned, config)

        async with self._session_factory() as session:
            # RSN → discord_user_id lookup
            rsn_map_result = await session.execute(
                select(UserAccount.discord_user_id, UserAccount.rsn)
            )
            rsn_to_user: dict[str, int] = {
                row.rsn.lower(): row.discord_user_id for row in rsn_map_result
            }

            # Upsert snapshots
            if snapshot_rows:
                snap_stmt = pg_insert(PlayerSnapshot).values(snapshot_rows)
                await session.execute(
                    snap_stmt.on_conflict_do_update(
                        index_elements=["rsn"],
                        set_={
                            "skills": snap_stmt.excluded.skills,
                            "bosses": snap_stmt.excluded.bosses,
                            "fetched_at": snap_stmt.excluded.fetched_at,
                        },
                    )
                )

            # Upsert rankings
            ranking_rows = [
                {
                    "rsn": r["rsn"],
                    "rank": r["rank"],
                    "points": r["points"],
                    "boss_points": r["boss_points"],
                    "skill_points": r["skill_points"],
                    "discord_user_id": rsn_to_user.get(r["rsn"]),
                    "updated_at": now,
                }
                for r in ranked
            ]
            if ranking_rows:
                rank_stmt = pg_insert(PlayerRanking).values(ranking_rows)
                await session.execute(
                    rank_stmt.on_conflict_do_update(
                        index_elements=["rsn"],
                        set_={
                            "rank": rank_stmt.excluded.rank,
                            "points": rank_stmt.excluded.points,
                            "boss_points": rank_stmt.excluded.boss_points,
                            "skill_points": rank_stmt.excluded.skill_points,
                            "discord_user_id": rank_stmt.excluded.discord_user_id,
                            "updated_at": rank_stmt.excluded.updated_at,
                        },
                    )
                )

            await session.commit()

        self.last_run_at = now
        self.last_run_count = len(ranked)
        self.last_error = None
        logger.info("RankingService: ranked {} players", len(ranked))

    async def rank_from_config(self, config_override: dict) -> list[dict]:
        """Re-rank using stored snapshots and a given config. No DB writes."""
        if self._session_factory is None:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerSnapshot.rsn, PlayerSnapshot.skills, PlayerSnapshot.bosses)
            )
            snapshots = [
                {"rsn": row.rsn, "skills": row.skills, "bosses": row.bosses}
                for row in result
            ]
        return rank_from_snapshots(snapshots, config_override)
