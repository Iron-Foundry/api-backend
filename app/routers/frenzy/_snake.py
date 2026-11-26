"""The snake order of a frenzy captain draft, as pure functions of the pick number."""

from __future__ import annotations

FULL = "full"
TOP_PICKS = "top_picks"


def snake_slot(pick: int, team_count: int) -> int:
    """The drawn-order position whose turn it is at a 1-based pick number."""
    rnd, pos = divmod(pick - 1, team_count)
    return pos if rnd % 2 == 0 else team_count - 1 - pos


def manual_picks_left(
    mode: str, top_picks: int, next_pick: int, team_count: int, pool_size: int
) -> bool:
    """Whether a captain still makes the next pick, rather than the hand-out."""
    if pool_size == 0:
        return False
    return mode == FULL or next_pick <= top_picks * team_count


def hand_out(
    team_ids: list[int], start_pick: int, pool_ids: list[int]
) -> list[tuple[int, int, int]]:
    """Continue the snake from `start_pick` over a pool ordered strongest first.

    Returns `(signup_id, team_id, pick_number)` for every signup in the pool.
    """
    count = len(team_ids)
    return [
        (signup_id, team_ids[snake_slot(pick, count)], pick)
        for pick, signup_id in enumerate(pool_ids, start=start_pick)
    ]
