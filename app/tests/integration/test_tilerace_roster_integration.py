"""Real-DB round trip for the tile race roster: generate, edit, reset.

Guards the property the old scramble broke - signups survive team generation, so
an event can always be returned to bare signups.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    PlayerSnapshot,
    TileRaceEvent,
    TileRaceSignup,
    User,
    UserAccount,
)

pytestmark = pytest.mark.integration

_RAIDERS = {"raider one": 250, "raider two": 90}
_PLAYERS = [
    "raider one",
    "raider two",
    "skiller one",
    "skiller two",
    "skiller three",
    "skiller four",
    "skiller five",
]


async def _seed_event(engine: AsyncEngine) -> int:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        event = TileRaceEvent(
            name="Roster Test",
            signups_open=True,
            cells=[],
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        event_id = event.id
        for index, rsn in enumerate(_PLAYERS):
            session.add(
                TileRaceSignup(
                    event_id=event_id,
                    discord_user_id=9000 + index,
                    rsn=rsn,
                    ranking_score=(len(_PLAYERS) - index) * 100,
                    wants_captain=index == 0,
                    signed_up_at=now,
                )
            )
            session.add(
                PlayerSnapshot(
                    rsn=rsn,
                    skills={},
                    bosses={"chambers_of_xeric": _RAIDERS.get(rsn, 0)},
                    activities={},
                    fetched_at=now,
                )
            )
        await session.commit()
        return event_id


async def _signup_rows(
    engine: AsyncEngine, event_id: int
) -> list[sa.Row[tuple[str, int | None, bool]]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT rsn, team_id, is_captain FROM tilerace_signups "
                "WHERE event_id = :e ORDER BY rsn"
            ),
            {"e": event_id},
        )
        return list(result)


async def test_generate_keeps_signups_and_reset_restores_the_pool(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)

    resp = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate",
        json={"team_size": 3, "balance_raids_kc": True, "raids_kc_threshold": 50},
    )
    assert resp.status_code == 200, resp.text
    teams = resp.json()["teams"]
    assert [len(t["members"]) for t in teams] == [3, 2, 2]

    rows = await _signup_rows(seed_engine, event_id)
    assert len(rows) == len(_PLAYERS), "generation must never delete a signup"
    assert all(r.team_id is not None for r in rows)
    assert sum(1 for r in rows if r.is_captain) == len(teams)

    detail = (await staff_client.get(f"/tilerace/events/{event_id}")).json()
    assert len(detail["signups"]) == len(_PLAYERS)
    assert sum(len(t["members"]) for t in detail["teams"]) == len(_PLAYERS)

    reset = await staff_client.post(f"/tilerace/events/{event_id}/teams/reset")
    assert reset.status_code == 200

    rows = await _signup_rows(seed_engine, event_id)
    assert len(rows) == len(_PLAYERS)
    assert all(r.team_id is None and not r.is_captain for r in rows), (
        "reset must return every member to the unassigned pool"
    )
    after = (await staff_client.get(f"/tilerace/events/{event_id}")).json()
    assert all(not t["members"] for t in after["teams"])


async def test_raids_balance_spreads_the_raiders(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)

    resp = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate",
        json={"team_size": 4, "balance_raids_kc": True, "raids_kc_threshold": 50},
    )
    assert resp.status_code == 200, resp.text
    teams = resp.json()["teams"]
    assert len(teams) == 2
    for team in teams:
        assert any(m["raids_kc"] >= 50 for m in team["members"]), (
            f"{team['name']} ended up without a raider"
        )


async def test_staff_can_add_move_and_remove_a_non_signup(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    now = datetime.now(UTC)
    async with AsyncSession(seed_engine) as session:
        session.add(
            User(
                discord_user_id=4242,
                discord_username="Replacement",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserAccount(
                discord_user_id=4242,
                rsn="Late Replacement",
                is_primary=True,
                created_at=now,
            )
        )
        await session.commit()

    candidates = await staff_client.get(
        f"/tilerace/events/{event_id}/roster/candidates?search=Replacement"
    )
    assert candidates.status_code == 200
    assert [c["discord_user_id"] for c in candidates.json()] == ["4242"]

    added = await staff_client.post(
        f"/tilerace/events/{event_id}/roster", json={"discord_user_id": "4242"}
    )
    assert added.status_code == 201, added.text
    assert added.json()["rsn"] == "Late Replacement"
    assert added.json()["added_by_staff"] is True
    assert added.json()["team_id"] is None

    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 4}
    )
    assert generated.status_code == 200, generated.text
    team_ids = [t["id"] for t in generated.json()["teams"]]

    moved = await staff_client.patch(
        f"/tilerace/events/{event_id}/roster/4242",
        json={"team_id": int(team_ids[1]), "is_captain": True},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["team_id"] == team_ids[1]

    detail = (await staff_client.get(f"/tilerace/events/{event_id}")).json()
    target = next(t for t in detail["teams"] if t["id"] == team_ids[1])
    captains = [m for m in target["members"] if m["is_captain"]]
    assert [c["rsn"] for c in captains] == ["Late Replacement"], (
        "promoting a captain must demote the previous one"
    )

    removed = await staff_client.delete(f"/tilerace/events/{event_id}/roster/4242")
    assert removed.status_code == 200
    rows = await _signup_rows(seed_engine, event_id)
    assert "Late Replacement" not in [r.rsn for r in rows]


async def _captain_counts(engine: AsyncEngine, event_id: int) -> dict[int, int]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT team_id, count(*) AS n FROM tilerace_signups "
                "WHERE event_id = :e AND is_captain GROUP BY team_id"
            ),
            {"e": event_id},
        )
        return {row.team_id: row.n for row in result}


async def test_appointing_a_captain_demotes_the_previous_one(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 4}
    )
    assert generated.status_code == 200, generated.text
    team = generated.json()["teams"][0]
    incumbent = next(m for m in team["members"] if m["is_captain"])
    challenger = next(m for m in team["members"] if not m["is_captain"])

    resp = await staff_client.patch(
        f"/tilerace/events/{event_id}/roster/{challenger['discord_user_id']}",
        json={"is_captain": True},
    )
    assert resp.status_code == 200, resp.text

    counts = await _captain_counts(seed_engine, event_id)
    assert counts[int(team["id"])] == 1
    detail = (await staff_client.get(f"/tilerace/events/{event_id}")).json()
    updated = next(t for t in detail["teams"] if t["id"] == team["id"])
    captains = [m["discord_user_id"] for m in updated["members"] if m["is_captain"]]
    assert captains == [challenger["discord_user_id"]]
    assert incumbent["discord_user_id"] not in captains


async def test_any_member_can_be_appointed_captain(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    """Not enough volunteers is fine - staff can promote anyone on the team."""
    event_id = await _seed_event(seed_engine)
    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 4}
    )
    assert generated.status_code == 200, generated.text
    team = generated.json()["teams"][0]

    for member in team["members"]:
        resp = await staff_client.patch(
            f"/tilerace/events/{event_id}/roster/{member['discord_user_id']}",
            json={"is_captain": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_captain"] is True
        counts = await _captain_counts(seed_engine, event_id)
        assert counts[int(team["id"])] == 1, "a team may never hold two captains"


async def test_moving_a_captain_does_not_give_the_new_team_two(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 4}
    )
    assert generated.status_code == 200, generated.text
    teams = generated.json()["teams"]
    source, target = teams[0], teams[1]
    captain = next(m for m in source["members"] if m["is_captain"])

    resp = await staff_client.patch(
        f"/tilerace/events/{event_id}/roster/{captain['discord_user_id']}",
        json={"team_id": int(target["id"])},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_captain"] is False, (
        "a captain moved to another team must lose the badge"
    )

    counts = await _captain_counts(seed_engine, event_id)
    assert counts.get(int(target["id"]), 0) == 1
    assert counts.get(int(source["id"]), 0) == 0


async def test_unassigned_member_cannot_be_captain(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 4}
    )
    assert generated.status_code == 200, generated.text
    captain = next(
        m for m in generated.json()["teams"][0]["members"] if m["is_captain"]
    )
    user_id = captain["discord_user_id"]

    unassign = await staff_client.patch(
        f"/tilerace/events/{event_id}/roster/{user_id}", json={"team_id": None}
    )
    assert unassign.status_code == 200
    assert unassign.json()["is_captain"] is False

    resp = await staff_client.patch(
        f"/tilerace/events/{event_id}/roster/{user_id}", json={"is_captain": True}
    )
    assert resp.status_code == 409


async def test_generate_leaves_exactly_one_captain_per_team(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    for size in (3, 2, 4, 3):
        resp = await staff_client.post(
            f"/tilerace/events/{event_id}/teams/generate", json={"team_size": size}
        )
        assert resp.status_code == 200, resp.text
        teams = resp.json()["teams"]
        for team in teams:
            captains = [m for m in team["members"] if m["is_captain"]]
            assert len(captains) == 1, f"{team['name']} has {len(captains)} captains"
        counts = await _captain_counts(seed_engine, event_id)
        assert sorted(counts.values()) == [1] * len(teams)


async def test_deleting_a_team_returns_members_to_the_pool(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_event(seed_engine)
    generated = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/generate", json={"team_size": 3}
    )
    assert generated.status_code == 200, generated.text
    doomed = generated.json()["teams"][0]

    resp = await staff_client.delete(
        f"/tilerace/events/{event_id}/teams/{doomed['id']}"
    )
    assert resp.status_code == 200

    rows = await _signup_rows(seed_engine, event_id)
    assert len(rows) == len(_PLAYERS), "deleting a team must not delete its members"
    assert sum(1 for r in rows if r.team_id is None) == len(doomed["members"])
