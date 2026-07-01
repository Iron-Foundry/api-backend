"""Constants and default RankingConfig for the ranking service."""

from __future__ import annotations

import os

from ._boss_defaults import DEFAULT_BOSS_METRICS
from ._skill_defaults import DEFAULT_PRESTIGE_METRICS, DEFAULT_SKILL_METRICS
from .scoring import RankingConfig

POLL_INTERVAL = 86400

_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_GLOBAL_GUILD_ID = 0
_RANKING_CONFIG_KEY = "ranking_config"

_DEFAULT_RANK_THRESHOLDS: dict[str, int] = {
    "rank_1": 0,
    "rank_2": 10000,
    "rank_3": 20000,
    "rank_4": 30000,
    "rank_5": 45000,
    "rank_6": 60000,
}

_DEFAULT_CONFIG = RankingConfig(
    bosses=DEFAULT_BOSS_METRICS,
    skills=DEFAULT_SKILL_METRICS,
    prestige=DEFAULT_PRESTIGE_METRICS,
    rank_thresholds=_DEFAULT_RANK_THRESHOLDS,
)
