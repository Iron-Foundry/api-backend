from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringResult:
    points: int
    boss_points: int
    skill_points: int
    rank: str
