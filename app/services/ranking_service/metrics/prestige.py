from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrestigeMetric:
    boss_name: str
    multiplier: float

    def to_dict(self) -> dict[str, Any]:
        return {"boss_name": self.boss_name, "multiplier": self.multiplier}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PrestigeMetric":
        return cls(
            boss_name=d["boss_name"],
            multiplier=float(d["multiplier"]),
        )


class PrestigeMetricBuilder:
    """Fluent builder for PrestigeMetric instances."""

    def __init__(self, boss_name: str) -> None:
        self._boss_name = boss_name
        self._multiplier: float = 1.0

    def multiplier(self, value: float) -> "PrestigeMetricBuilder":
        self._multiplier = value
        return self

    def build(self) -> PrestigeMetric:
        if not self._boss_name:
            raise ValueError("PrestigeMetric boss_name is required")
        if self._multiplier <= 0:
            raise ValueError("multiplier must be positive")
        return PrestigeMetric(boss_name=self._boss_name, multiplier=self._multiplier)
