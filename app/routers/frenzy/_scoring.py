from __future__ import annotations

from typing import Any

from app.db.models import FrenzyTeam, FrenzyTemplate

from ._points import round_half_up


def _calc_item_points(item: dict[str, Any], obtained: int) -> int:
    pts = 0
    base_pts: int = round_half_up(item.get("points", 0))
    dup_pts: int = round_half_up(base_pts / 2)
    required: int = item.get("required", 1)
    dup_required: int = item.get("duplicate_required", 1)

    if obtained >= required:
        pts += base_pts
    elif required == 2 and obtained == 1:
        pts += round_half_up(base_pts / 2)

    beyond = obtained - required
    if beyond >= dup_required:
        pts += dup_pts
    elif dup_required == 2 and beyond == 1:
        pts += round_half_up(dup_pts / 2)

    return pts


_calc_item_pts = _calc_item_points


def _calc_tier_entry_points(entry: dict[str, Any], current_value: float) -> int:
    tiers_done = sum(
        1
        for t in ["tier1", "tier2", "tier3", "tier4"]
        if current_value >= entry.get(t, 0)
    )
    base = entry.get("point_step", 0) * tiers_done
    if current_value >= entry.get("tier4", 0) and tiers_done == 4:
        return round_half_up(base * entry.get("multiplier", 1))
    return round_half_up(base)


def _is_multiplier_unlocked(
    mult: dict[str, Any], item_progress: dict[str, Any]
) -> bool:
    return all(item_progress.get(r, 0) > 0 for r in mult.get("requirement", []))


def _unlocked_factors(
    template: FrenzyTemplate, item_progress: dict[str, Any]
) -> dict[str, float]:
    factors: dict[str, float] = {}
    for m in template.multipliers or []:
        if not _is_multiplier_unlocked(m, item_progress):
            continue
        for src in m.get("affects", []):
            factors[src] = factors.get(src, 1.0) * m.get("factor", 1.0)
    return factors


def _tier_points(
    template: FrenzyTemplate, item_progress: dict[str, Any]
) -> dict[str, int]:
    factors = _unlocked_factors(template, item_progress)
    tier_pts: dict[str, int] = {}
    for tier_name, tier_data in (template.tiers or {}).items():
        t_pts = 0
        for source in tier_data.get("sources", []):
            src_name: str = source.get("name", "")
            src_pts = sum(
                _calc_item_pts(
                    item,
                    item_progress.get(
                        f"{tier_name}.{src_name}.{item.get('name', '')}", 0
                    ),
                )
                for item in source.get("items", [])
            )
            t_pts += round_half_up(src_pts * factors.get(src_name, 1.0))
        tier_pts[tier_name] = t_pts
    return tier_pts


def _compute_scores_from_progress(
    template: FrenzyTemplate,
    item_progress: dict[str, Any],
    activity_progress: dict[str, Any],
    milestone_progress: dict[str, Any],
) -> dict[str, Any]:
    tier_pts = _tier_points(template, item_progress)

    activity_pts = sum(
        _calc_tier_entry_points(act, activity_progress.get(act.get("name", ""), 0))
        for act in (template.activities or [])
    )

    milestone_pts = sum(
        _calc_tier_entry_points(entry, milestone_progress.get(entry.get("name", ""), 0))
        for entries in (template.milestones or {}).values()
        for entry in entries
    )

    return {
        "tier_points": tier_pts,
        "activity_points": activity_pts,
        "milestone_points": milestone_pts,
        "total": sum(tier_pts.values()) + activity_pts + milestone_pts,
    }


def _compute_team_scores(template: FrenzyTemplate, team: FrenzyTeam) -> dict[str, Any]:
    return _compute_scores_from_progress(
        template,
        team.item_progress or {},
        team.activity_progress or {},
        team.milestone_progress or {},
    )
