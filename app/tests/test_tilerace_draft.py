from __future__ import annotations

from dataclasses import dataclass

from app.routers.tilerace._draft import (
    balance_raiders,
    pick_captain,
    raids_kc,
    snake_draft,
    target_sizes,
    team_count_for,
)


@dataclass
class FakeSignup:
    id: int
    rsn: str
    ranking_score: int
    wants_captain: bool = False


def _pool(count: int) -> list[FakeSignup]:
    return [
        FakeSignup(id=i, rsn=f"p{i:02d}", ranking_score=1000 - i) for i in range(count)
    ]


def test_team_size_is_a_hard_maximum() -> None:
    assert target_sizes(23, 5) == [5, 5, 5, 5, 3]
    assert target_sizes(22, 5) == [5, 5, 5, 5, 2]
    assert target_sizes(13, 4) == [4, 4, 4, 1]
    assert target_sizes(20, 5) == [5, 5, 5, 5]


def test_team_count_edges() -> None:
    assert team_count_for(0, 5) == 0
    assert team_count_for(10, 0) == 0
    assert team_count_for(1, 5) == 1


def test_draft_respects_capacities_and_places_everyone() -> None:
    pool = _pool(23)
    capacities = target_sizes(len(pool), 5)
    team_ids = [10, 20, 30, 40, 50]
    result = snake_draft(pool, team_ids, capacities)  # type: ignore[arg-type]
    assert [len(result[t]) for t in team_ids] == capacities
    placed = [s for members in result.values() for s in members]
    assert len(placed) == len(pool)
    assert {s.id for s in placed} == {s.id for s in pool}


def test_draft_spreads_strength() -> None:
    pool = _pool(12)
    team_ids = [1, 2, 3]
    result = snake_draft(pool, team_ids, [4, 4, 4])  # type: ignore[arg-type]
    totals = [sum(s.ranking_score for s in result[t]) for t in team_ids]
    assert max(totals) - min(totals) <= 4


def test_draft_rejects_insufficient_capacity() -> None:
    try:
        snake_draft(_pool(5), [1], [2])  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_raids_kc_takes_the_highest_single_raid() -> None:
    assert raids_kc(None) == 0
    assert raids_kc({}) == 0
    assert raids_kc({"chambers_of_xeric": 40, "tombs_of_amascut": 120}) == 120
    assert raids_kc({"theatre_of_blood_hard_mode": 7, "zulrah": 5000}) == 7
    assert raids_kc({"chambers_of_xeric": -1}) == 0


def test_balance_gives_every_team_a_raider() -> None:
    pool = _pool(6)
    assignments = {1: pool[0:2], 2: pool[2:4], 3: pool[4:6]}
    raiders = {pool[0].id, pool[1].id, pool[2].id}
    balance_raiders(assignments, raiders)  # type: ignore[arg-type]
    assert all(
        any(s.id in raiders for s in members) for members in assignments.values()
    )
    assert [len(m) for m in assignments.values()] == [2, 2, 2]


def test_balance_stops_when_raiders_run_out() -> None:
    pool = _pool(6)
    assignments = {1: pool[0:2], 2: pool[2:4], 3: pool[4:6]}
    raiders = {pool[0].id}
    balance_raiders(assignments, raiders)  # type: ignore[arg-type]
    covered = sum(
        1 for members in assignments.values() if any(s.id in raiders for s in members)
    )
    assert covered == 1
    assert [len(m) for m in assignments.values()] == [2, 2, 2]


def test_captain_prefers_a_volunteer() -> None:
    weak_volunteer = FakeSignup(id=1, rsn="a", ranking_score=10, wants_captain=True)
    strong = FakeSignup(id=2, rsn="b", ranking_score=900)
    assert pick_captain([weak_volunteer, strong]) == 1  # type: ignore[arg-type]
    assert pick_captain([strong]) == 2  # type: ignore[arg-type]
    assert pick_captain([]) is None
