from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzySubmission, FrenzyTeam, FrenzyTemplate


def _calc_item_points(item: dict[str, Any], obtained: int) -> int:
    pts = 0
    base_pts: int = round(item.get("points", 0))
    dup_pts: int = round(base_pts / 2)
    required: int = item.get("required", 1)
    dup_required: int = item.get("duplicate_required", 1)

    if obtained >= required:
        pts += base_pts
    elif required == 2 and obtained == 1:
        pts += round(base_pts / 2)

    beyond = obtained - required
    if beyond >= dup_required:
        pts += dup_pts
    elif dup_required == 2 and beyond == 1:
        pts += round(dup_pts / 2)

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
        return round(base * entry.get("multiplier", 1))
    return base


def _is_multiplier_unlocked(
    mult: dict[str, Any], item_progress: dict[str, Any]
) -> bool:
    return all(item_progress.get(r, 0) > 0 for r in mult.get("requirement", []))


def _compute_scores_from_progress(
    template: FrenzyTemplate,
    item_progress: dict[str, Any],
    activity_progress: dict[str, Any],
    milestone_progress: dict[str, Any],
) -> dict[str, Any]:
    multipliers: list[Any] = template.multipliers or []
    unlocked_mults = [
        m for m in multipliers if _is_multiplier_unlocked(m, item_progress)
    ]
    unlocked_affects: dict[str, float] = {}
    for m in unlocked_mults:
        for src in m.get("affects", []):
            unlocked_affects[src] = unlocked_affects.get(src, 1.0) * m.get(
                "factor", 1.0
            )

    tier_pts: dict[str, float] = {}
    for tier_name, tier_data in (template.tiers or {}).items():
        t_pts = 0.0
        for source in tier_data.get("sources", []):
            src_pts = 0.0
            src_name: str = source.get("name", "")
            for item in source.get("items", []):
                item_key = f"{tier_name}.{src_name}.{item.get('name', '')}"
                obtained = item_progress.get(item_key, 0)
                src_pts += _calc_item_pts(item, obtained)
            t_pts += src_pts * unlocked_affects.get(src_name, 1.0)
        tier_pts[tier_name] = t_pts

    activity_pts = sum(
        _calc_tier_entry_points(act, activity_progress.get(act.get("name", ""), 0))
        for act in (template.activities or [])
    )

    milestone_pts = 0.0
    for entries in (template.milestones or {}).values():
        for entry in entries:
            milestone_pts += _calc_tier_entry_points(
                entry, milestone_progress.get(entry.get("name", ""), 0)
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


def _apply_pending_submissions(
    base_item: dict[str, Any],
    base_activity: dict[str, Any],
    base_milestone: dict[str, Any],
    pending: Sequence[FrenzySubmission],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    item_p = dict(base_item)
    act_by_player: dict[str, dict[int, int]] = {}
    mil_by_player: dict[str, dict[int, int]] = {}

    for sub in pending:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_p[key] = item_p.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            act_by_player.setdefault(name, {})
            act_by_player[name][uid] = max(
                act_by_player[name].get(uid, 0), p.get("value", 0)
            )
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            mil_by_player.setdefault(name, {})
            mil_by_player[name][uid] = max(
                mil_by_player[name].get(uid, 0), p.get("value", 0)
            )

    act_p = dict(base_activity)
    for name, by_player in act_by_player.items():
        act_p[name] = act_p.get(name, 0) + sum(by_player.values())

    mil_p = dict(base_milestone)
    for name, by_player in mil_by_player.items():
        mil_p[name] = mil_p.get(name, 0) + sum(by_player.values())

    return item_p, act_p, mil_p


async def _recompute_team_progress(session: AsyncSession, team: FrenzyTeam) -> None:
    """Rebuild team JSONB caches from all approved submissions for this team."""
    submissions = (
        (
            await session.execute(
                select(FrenzySubmission)
                .where(
                    FrenzySubmission.team_id == team.id,
                    FrenzySubmission.status == "approved",
                )
                .order_by(FrenzySubmission.submitted_at)
            )
        )
        .scalars()
        .all()
    )

    item_progress: dict[str, int] = {}
    activity_by_player: dict[str, dict[int, int]] = {}
    milestone_by_player: dict[str, dict[int, int]] = {}

    for sub in submissions:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = f"{p['tier']}.{p['source_name']}.{p['item_name']}"
            item_progress[key] = item_progress.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            name = p["name"]
            uid = sub.discord_user_id
            activity_by_player.setdefault(name, {})
            activity_by_player[name][uid] = max(
                activity_by_player[name].get(uid, 0), p.get("value", 0)
            )
        elif sub.submission_type == "milestone":
            name = p["name"]
            uid = sub.discord_user_id
            milestone_by_player.setdefault(name, {})
            milestone_by_player[name][uid] = max(
                milestone_by_player[name].get(uid, 0), p.get("value", 0)
            )

    team.item_progress = item_progress
    team.activity_progress = {n: sum(v.values()) for n, v in activity_by_player.items()}
    team.milestone_progress = {
        n: sum(v.values()) for n, v in milestone_by_player.items()
    }
    team.updated_at = datetime.now(UTC)


def _recalculate_tier_points(
    tiers: dict[str, Any], total_point_cap: int
) -> dict[str, Any]:
    import copy

    result = copy.deepcopy(tiers)
    for tier_data in result.values():
        budget_pct = tier_data.get("budget_pct", 0)
        tier_budget = round((budget_pct / 100) * total_point_cap)
        eligible: list[tuple[dict[str, Any], float]] = []
        for source in tier_data.get("sources", []):
            for item in source.get("items", []):
                d = item.get("drop_denom")
                k = item.get("kph")
                if d and k and not item.get("points_locked", False):
                    eligible.append((item, d / k))
        tier_hd_sum = sum(hd for _, hd in eligible)
        if tier_hd_sum > 0:
            for item, hd in eligible:
                item["points"] = round((hd / tier_hd_sum) * tier_budget)
    return result
