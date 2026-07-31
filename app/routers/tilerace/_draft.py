from __future__ import annotations

import math
from typing import Any

from app.db.models import TileRaceSignup

RAID_METRICS = (
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert",
)


def team_count_for(signup_count: int, team_size: int) -> int:
    """Number of teams needed so that no team exceeds team_size."""
    if signup_count <= 0 or team_size <= 0:
        return 0
    return math.ceil(signup_count / team_size)


def target_sizes(signup_count: int, team_size: int) -> list[int]:
    """Per-team capacities: teams filled to team_size, the last takes the remainder."""
    teams = team_count_for(signup_count, team_size)
    if not teams:
        return []
    full, remainder = divmod(signup_count, team_size)
    sizes = [team_size] * full
    if remainder:
        sizes.append(remainder)
    return sizes


def snake_draft(
    signups: list[TileRaceSignup], team_ids: list[int], capacities: list[int]
) -> dict[int, list[TileRaceSignup]]:
    """Distribute signups strongest-first in snake order, respecting each capacity."""
    result: dict[int, list[TileRaceSignup]] = {tid: [] for tid in team_ids}
    n = len(team_ids)
    if not n:
        return result
    caps = {
        tid: capacities[i] if i < len(capacities) else 0
        for i, tid in enumerate(team_ids)
    }
    ordered = sorted(signups, key=lambda s: (-s.ranking_score, s.rsn.lower()))
    if sum(caps.values()) < len(ordered):
        raise ValueError("Not enough team capacity for every signup.")
    picks = 0
    for signup in ordered:
        placed = False
        while not placed:
            chunk, pos = divmod(picks, n)
            idx = pos if chunk % 2 == 0 else n - 1 - pos
            tid = team_ids[idx]
            picks += 1
            if len(result[tid]) < caps[tid]:
                result[tid].append(signup)
                placed = True
    return result


def raids_kc(bosses: dict[str, Any] | None) -> int:
    """Highest single-raid kill count across CoX, ToB and ToA including variants."""
    if not bosses:
        return 0
    return max(int(bosses.get(metric) or 0) for metric in RAID_METRICS)


def _needs_raider(
    assignments: dict[int, list[TileRaceSignup]], raiders: set[int], team_id: int
) -> bool:
    return not any(s.id in raiders for s in assignments[team_id])


def balance_raiders(
    assignments: dict[int, list[TileRaceSignup]], raiders: set[int]
) -> None:
    """Swap members so every team holds at least one raider, where supply allows.

    Swaps preserve team sizes and always trade the lowest-ranked spare raider for
    the lowest-ranked non-raider on the receiving team, so scores stay close.
    """
    for team_id in assignments:
        if not _needs_raider(assignments, raiders, team_id):
            continue
        donor = _find_donor(assignments, raiders, team_id)
        if donor is None:
            return
        donor_team, raider = donor
        receiver = assignments[team_id]
        swap_out = min(receiver, key=lambda s: s.ranking_score)
        assignments[donor_team].remove(raider)
        receiver.remove(swap_out)
        assignments[donor_team].append(swap_out)
        receiver.append(raider)


def _find_donor(
    assignments: dict[int, list[TileRaceSignup]], raiders: set[int], skip: int
) -> tuple[int, TileRaceSignup] | None:
    best: tuple[int, TileRaceSignup] | None = None
    for team_id, members in assignments.items():
        if team_id == skip:
            continue
        team_raiders = [s for s in members if s.id in raiders]
        if len(team_raiders) < 2:
            continue
        spare = min(team_raiders, key=lambda s: s.ranking_score)
        if best is None or spare.ranking_score < best[1].ranking_score:
            best = (team_id, spare)
    return best


def pick_captain(members: list[TileRaceSignup]) -> int | None:
    """Prefer a volunteer, otherwise the highest-ranked member."""
    if not members:
        return None
    volunteers = [s for s in members if s.wants_captain]
    pool = volunteers or members
    return max(pool, key=lambda s: s.ranking_score).id
