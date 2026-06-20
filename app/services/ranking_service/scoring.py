"""Pure ranking computation - no DB or network access."""

from __future__ import annotations


_RANK_ORDER = {
    "No Rank": 0,
    "Rank 1": 1,
    "Rank 2": 2,
    "Rank 3": 3,
    "Rank 4": 4,
    "Rank 5": 5,
    "Rank 6": 6,
}


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


def rank_from_snapshots(snapshots: list[dict], config: dict) -> list[dict]:
    """Compute rankings from player snapshots and a config dict.

    Returns list of {rsn, rank, points, boss_points, skill_points}.
    No DB or network access.
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

        boss_raw = 0.0
        for tier_key, boss_names in tier_boss_lists.items():
            mult_key = f"tier_{tier_key[1]}"
            kcs = {b: bosses[b] for b in boss_names if b in bosses}
            boss_raw += _tier_avg(kcs, kc_tiers, tier_mults[mult_key])
        for raid_key, raid_names in raid_lists.items():
            kcs = {b: bosses[b] for b in raid_names if b in bosses}
            boss_raw += _tier_avg(kcs, kc_tiers, tier_mults[raid_key])

        tracked = {s: float(v) for s, v in skills.items() if s in skill_names}
        skill_raw = (
            sum(_skill_score(exp, exp_tiers) for exp in tracked.values()) / len(tracked)
            if tracked
            else 0.0
        )

        raw = (boss_raw * mults["boss"] + skill_raw * mults["skill"]) / 2
        points = int(raw * 1000)
        results.append(
            {
                "rsn": rsn,
                "rank": _assign_rank(points, thresholds),
                "points": points,
                "boss_points": int(boss_raw * mults["boss"] * 1000 / 2),
                "skill_points": int(skill_raw * mults["skill"] * 1000 / 2),
            }
        )

    results.sort(key=lambda p: (-_RANK_ORDER.get(p["rank"], 0), -p["points"]))
    return results
