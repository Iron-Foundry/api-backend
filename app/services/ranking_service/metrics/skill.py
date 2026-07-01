from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

_XP_99 = 13_034_431
_XP_200M = 200_000_000


@dataclass(frozen=True)
class SkillMetric:
    name: str
    points_per_million_xp: float
    milestone_99_bonus: float
    milestone_200m_bonus: float
    log_scale: bool

    def score(self, xp: float) -> float:
        if xp <= 0:
            return 0.0
        millions = xp / 1_000_000
        if self.log_scale:
            xp_points = self.points_per_million_xp * math.log1p(millions)
        else:
            xp_points = self.points_per_million_xp * millions
        milestones = (self.milestone_99_bonus if xp >= _XP_99 else 0.0) + (
            self.milestone_200m_bonus if xp >= _XP_200M else 0.0
        )
        return xp_points + milestones

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "points_per_million_xp": self.points_per_million_xp,
            "milestone_99_bonus": self.milestone_99_bonus,
            "milestone_200m_bonus": self.milestone_200m_bonus,
            "log_scale": self.log_scale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SkillMetric":
        return cls(
            name=d["name"],
            points_per_million_xp=float(d.get("points_per_million_xp", 2.0)),
            milestone_99_bonus=float(d.get("milestone_99_bonus", 0.0)),
            milestone_200m_bonus=float(d.get("milestone_200m_bonus", 0.0)),
            log_scale=bool(d.get("log_scale", False)),
        )


class SkillMetricBuilder:
    """Fluent builder for SkillMetric instances."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._points_per_million_xp: float = 2.0
        self._milestone_99_bonus: float = 0.0
        self._milestone_200m_bonus: float = 0.0
        self._log_scale: bool = False

    def points_per_million_xp(self, value: float) -> "SkillMetricBuilder":
        self._points_per_million_xp = value
        return self

    def milestone_99_bonus(self, value: float) -> "SkillMetricBuilder":
        self._milestone_99_bonus = value
        return self

    def milestone_200m_bonus(self, value: float) -> "SkillMetricBuilder":
        self._milestone_200m_bonus = value
        return self

    def with_log_scale(self) -> "SkillMetricBuilder":
        self._log_scale = True
        return self

    def build(self) -> SkillMetric:
        if not self._name:
            raise ValueError("SkillMetric name is required")
        return SkillMetric(
            name=self._name,
            points_per_million_xp=self._points_per_million_xp,
            milestone_99_bonus=self._milestone_99_bonus,
            milestone_200m_bonus=self._milestone_200m_bonus,
            log_scale=self._log_scale,
        )
