"""Normalises WOM efficiency-rate responses into flat rate rows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RateRow:
    metric: str
    kind: str
    rate: float
    payload: dict = field(default_factory=dict)


def parse_ehb(entries: list[dict]) -> list[RateRow]:
    """Boss rates arrive as a flat list of {boss, rate} (kills per hour)."""
    rows: list[RateRow] = []
    for entry in entries:
        boss = entry.get("boss")
        rate = entry.get("rate")
        if isinstance(boss, str) and isinstance(rate, (int, float)):
            rows.append(RateRow(boss, "ehb", float(rate)))
    return rows


def parse_ehp(entries: list[dict]) -> list[RateRow]:
    """Skill rates carry tiered methods; store the peak xp/hr plus the full tiers."""
    rows: list[RateRow] = []
    for entry in entries:
        skill = entry.get("skill")
        methods = entry.get("methods") or []
        if not isinstance(skill, str):
            continue
        rates = [
            m["rate"]
            for m in methods
            if isinstance(m, dict) and isinstance(m.get("rate"), (int, float))
        ]
        peak = float(max(rates)) if rates else 0.0
        payload = {"methods": methods, "bonuses": entry.get("bonuses") or []}
        rows.append(RateRow(skill, "ehp", peak, payload))
    return rows
