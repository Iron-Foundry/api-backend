from __future__ import annotations

import copy
import math
from typing import Any

# `web-app/src/lib/frenzyPoints.ts` repeats this rule; `fixtures/frenzy_points.json`
# holds the cases both sides must agree on.
POINT_CAP = 1_000_000
FULL_COMPLETION_FACTOR = 1.5
_RETIRED_TIER_KEYS = ("budget_pct",)
_RETIRED_ITEM_KEYS = ("points_locked",)


def round_half_up(value: float) -> int:
    """Return `value` at the nearest whole number, with .5 rounding up."""
    return math.floor(value + 0.5)


def hours_per_drop(item: dict[str, Any]) -> float | None:
    """Return the hours one drop of `item` takes, or None without both rates."""
    denom = item.get("drop_denom")
    kph = item.get("kph")
    if not denom or not kph:
        return None
    return denom / kph


def tier_multiplier(tier: dict[str, Any]) -> float:
    """Return the tier's point multiplier, 1 when unset."""
    value = tier.get("multiplier")
    return float(value) if value else 1.0


def ordered_tiers(tiers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return the tiers by their `order`; a tier with none keeps its stored place.

    Postgres JSONB sorts object keys by length, then by bytes, so the stored key
    order is never the order staff set.
    """
    entries = list(tiers.items())
    return [
        entries[i]
        for i in sorted(
            range(len(entries)),
            key=lambda i: (entries[i][1].get("order", i), i),
        )
    ]


def _all_items(tiers: dict[str, Any]) -> list[tuple[dict[str, Any], float]]:
    return [
        (item, tier_multiplier(tier))
        for tier in tiers.values()
        for source in tier.get("sources", [])
        for item in source.get("items", [])
    ]


def _drop_retired_keys(tiers: dict[str, Any]) -> None:
    for tier in tiers.values():
        for key in _RETIRED_TIER_KEYS:
            tier.pop(key, None)
    for item, _ in _all_items(tiers):
        for key in _RETIRED_ITEM_KEYS:
            item.pop(key, None)


def assign_item_points(tiers: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `tiers` with each item's points set from the fixed cap.

    An item's share follows its hours per drop. Full completion counts the
    duplicate, which scores half the base points, so the base points of all items
    sum to the cap divided by 1.5. A tier's `multiplier` then scales its items'
    points above that base. Event multipliers are outside the cap. An item with no
    drop rate or no kill rate scores 0. Each tier's `order` is set to its place.
    Budget and lock keys are dropped.
    """
    result = copy.deepcopy(tiers)
    _drop_retired_keys(result)
    for place, (_, tier) in enumerate(ordered_tiers(result)):
        tier["order"] = place
    items = _all_items(result)
    hours = [hours_per_drop(item) for item, _ in items]
    total = sum(h for h in hours if h is not None)
    base_pool = POINT_CAP / FULL_COMPLETION_FACTOR
    for (item, factor), h in zip(items, hours, strict=True):
        share = h / total * base_pool * factor if h and total else 0
        item["points"] = round_half_up(share)
    return result
