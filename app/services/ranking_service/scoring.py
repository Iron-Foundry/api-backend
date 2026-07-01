"""Pure ranking computation - no DB or network access."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .metrics import BossMetric, PrestigeMetric, SkillMetric

_RANK_ORDER: dict[str, int] = {"No Rank": 0, **{f"Rank {i}": i for i in range(1, 11)}}


@dataclass(frozen=True)
class RankingConfig:
    bosses: tuple[BossMetric, ...]
    skills: tuple[SkillMetric, ...]
    prestige: tuple[PrestigeMetric, ...]
    rank_thresholds: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "bosses": [m.to_dict() for m in self.bosses],
            "skills": [m.to_dict() for m in self.skills],
            "prestige": [p.to_dict() for p in self.prestige],
            "rank_thresholds": dict(self.rank_thresholds),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RankingConfig":
        return cls(
            bosses=tuple(BossMetric.from_dict(b) for b in d["bosses"]),
            skills=tuple(SkillMetric.from_dict(s) for s in d["skills"]),
            prestige=tuple(PrestigeMetric.from_dict(p) for p in d["prestige"]),
            rank_thresholds=dict(d["rank_thresholds"]),
        )


def _assign_rank(points: int, thresholds: dict[str, int]) -> str:
    if points <= 0:
        return "No Rank"
    for key, threshold in sorted(
        thresholds.items(), key=lambda kv: kv[1], reverse=True
    ):
        if points >= threshold:
            return f"Rank {key.removeprefix('rank_')}"
    return "No Rank"


def _apply_prestige(
    prestige: tuple[PrestigeMetric, ...],
    bosses: dict[str, int],
    base: float,
) -> float:
    multiplier = 1.0
    for p in prestige:
        if bosses.get(p.boss_name, 0) >= 1:
            multiplier *= p.multiplier
    return base * multiplier


def rank_from_snapshots(snapshots: list[dict], config: RankingConfig) -> list[dict]:
    """Compute rankings from player snapshots and a RankingConfig.

    Returns list of {rsn, rank, points, boss_points, skill_points}.
    No DB or network access.
    """
    results = []
    for snap in snapshots:
        rsn: str = snap["rsn"]
        bosses: dict[str, int] = snap.get("bosses", {})
        skills: dict[str, float] = snap.get("skills", {})

        boss_pts = sum(m.score(bosses.get(m.name, 0)) for m in config.bosses)
        skill_pts = sum(m.score(skills.get(m.name, 0.0)) for m in config.skills)

        base = boss_pts + skill_pts
        total = _apply_prestige(config.prestige, bosses, base)
        points = int(total)

        results.append(
            {
                "rsn": rsn,
                "rank": _assign_rank(points, config.rank_thresholds),
                "points": points,
                "boss_points": int(boss_pts),
                "skill_points": int(skill_pts),
            }
        )

    results.sort(key=lambda p: (-_RANK_ORDER.get(p["rank"], 0), -p["points"]))
    return results


def rank_player_breakdown(snapshot: dict, config: RankingConfig) -> dict:
    """Per-metric score breakdown for a single player snapshot. No DB or network access."""
    bosses: dict[str, int] = snapshot.get("bosses", {})
    skills: dict[str, float] = snapshot.get("skills", {})

    boss_entries: list[dict] = []
    for m in config.bosses:
        kc = bosses.get(m.name, 0)
        pts = m.score(kc)
        if kc <= 0 and pts <= 0.0:
            continue
        subsequent = max(0, kc - 1)
        fkb = m.first_kill_bonus if kc >= 1 else 0.0
        kc_pts = (
            m.points_per_kc * m.tier_weight * math.log1p(subsequent)
            if m.log_scale
            else m.points_per_kc * m.tier_weight * subsequent
        )
        boss_entries.append(
            {
                "name": m.name,
                "kc": kc,
                "points": round(pts, 2),
                "first_kill_bonus": round(fkb, 2),
                "kc_points": round(kc_pts, 2),
                "tier_weight": m.tier_weight,
            }
        )
    boss_entries.sort(key=lambda e: -e["points"])

    skill_entries: list[dict] = []
    for m in config.skills:
        xp = skills.get(m.name, 0.0)
        pts = m.score(xp)
        if xp <= 0.0 and pts <= 0.0:
            continue
        millions = xp / 1_000_000
        xp_pts = (
            m.points_per_million_xp * math.log1p(millions)
            if m.log_scale
            else m.points_per_million_xp * millions
        )
        m99 = m.milestone_99_bonus if xp >= 13_034_431 else 0.0
        m200 = m.milestone_200m_bonus if xp >= 200_000_000 else 0.0
        skill_entries.append(
            {
                "name": m.name,
                "xp": round(xp),
                "points": round(pts, 2),
                "xp_points": round(xp_pts, 2),
                "milestone_99": round(m99, 2),
                "milestone_200m": round(m200, 2),
            }
        )
    skill_entries.sort(key=lambda e: -e["points"])

    prestige_entries: list[dict] = []
    multiplier = 1.0
    for p in config.prestige:
        active = bosses.get(p.boss_name, 0) >= 1
        if active:
            multiplier *= p.multiplier
        prestige_entries.append(
            {"boss_name": p.boss_name, "multiplier": p.multiplier, "active": active}
        )

    boss_pts = sum(e["points"] for e in boss_entries)
    skill_pts = sum(e["points"] for e in skill_entries)
    base = boss_pts + skill_pts

    return {
        "bosses": boss_entries,
        "skills": skill_entries,
        "prestige": prestige_entries,
        "boss_points": int(boss_pts),
        "skill_points": int(skill_pts),
        "base_points": int(base),
        "prestige_multiplier": round(multiplier, 6),
        "total_points": int(base * multiplier),
    }
