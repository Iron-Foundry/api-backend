from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BossMetric:
    name: str
    points_per_kc: float
    first_kill_bonus: float
    tier_weight: float
    log_scale: bool

    def score(self, kc: int) -> float:
        if kc <= 0:
            return 0.0
        subsequent = max(0, kc - 1)
        if self.log_scale:
            kc_points = self.points_per_kc * self.tier_weight * math.log1p(subsequent)
        else:
            kc_points = self.points_per_kc * self.tier_weight * subsequent
        return self.first_kill_bonus + kc_points

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "points_per_kc": self.points_per_kc,
            "first_kill_bonus": self.first_kill_bonus,
            "tier_weight": self.tier_weight,
            "log_scale": self.log_scale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BossMetric:
        return cls(
            name=d["name"],
            points_per_kc=float(d.get("points_per_kc", 5.0)),
            first_kill_bonus=float(d.get("first_kill_bonus", 0.0)),
            tier_weight=float(d.get("tier_weight", 1.0)),
            log_scale=bool(d.get("log_scale", False)),
        )


class BossMetricBuilder:
    """Fluent builder for BossMetric instances."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._points_per_kc: float = 5.0
        self._first_kill_bonus: float = 0.0
        self._tier_weight: float = 1.0
        self._log_scale: bool = False

    def points_per_kc(self, value: float) -> BossMetricBuilder:
        self._points_per_kc = value
        return self

    def first_kill_bonus(self, value: float) -> BossMetricBuilder:
        self._first_kill_bonus = value
        return self

    def tier_weight(self, value: float) -> BossMetricBuilder:
        self._tier_weight = value
        return self

    def with_log_scale(self) -> BossMetricBuilder:
        self._log_scale = True
        return self

    def build(self) -> BossMetric:
        if not self._name:
            raise ValueError("BossMetric name is required")
        return BossMetric(
            name=self._name,
            points_per_kc=self._points_per_kc,
            first_kill_bonus=self._first_kill_bonus,
            tier_weight=self._tier_weight,
            log_scale=self._log_scale,
        )
