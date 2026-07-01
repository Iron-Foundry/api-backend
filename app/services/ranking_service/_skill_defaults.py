from __future__ import annotations

from .metrics.prestige import PrestigeMetric, PrestigeMetricBuilder
from .metrics.skill import SkillMetric, SkillMetricBuilder


def _s(
    name: str,
    ppm: float,
    m99: float = 200.0,
    m200: float = 300.0,
) -> SkillMetric:
    return (
        SkillMetricBuilder(name)
        .points_per_million_xp(ppm)
        .milestone_99_bonus(m99)
        .milestone_200m_bonus(m200)
        .build()
    )


def _p(boss_name: str, multiplier: float) -> PrestigeMetric:
    return PrestigeMetricBuilder(boss_name).multiplier(multiplier).build()


DEFAULT_SKILL_METRICS: tuple[SkillMetric, ...] = (
    _s("attack", 2.0),
    _s("strength", 2.0),
    _s("defence", 2.0),
    _s("ranged", 2.0),
    _s("magic", 2.0),
    _s("prayer", 2.0),
    _s("hitpoints", 2.0),
    _s("slayer", 3.0, m99=200.0, m200=500.0),
    _s("cooking", 1.5),
    _s("woodcutting", 1.5),
    _s("fletching", 1.5),
    _s("fishing", 2.0),
    _s("firemaking", 1.5),
    _s("crafting", 2.0),
    _s("smithing", 2.0),
    _s("mining", 2.0),
    _s("herblore", 3.0, m99=200.0, m200=500.0),
    _s("agility", 3.0, m99=200.0, m200=500.0),
    _s("thieving", 3.0, m99=200.0, m200=500.0),
    _s("farming", 3.0, m99=200.0, m200=500.0),
    _s("runecrafting", 3.0, m99=200.0, m200=500.0),
    _s("hunter", 3.0, m99=200.0, m200=500.0),
    _s("construction", 2.0),
    _s("sailing", 2.0),
)

DEFAULT_PRESTIGE_METRICS: tuple[PrestigeMetric, ...] = (
    _p("tzkal_zuk", 1.15),
    _p("sol_heredit", 1.10),
)
