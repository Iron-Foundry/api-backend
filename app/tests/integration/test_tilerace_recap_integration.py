"""Real-DB proof that the public recap counts only surviving racers.

A racer removed mid-event keeps their submission rows, so the recap has to
filter them out against the roster rather than trust the rows. These tests seed
a finished event with one removed author and pin what an anonymous caller sees.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceSubmission,
    TileRaceTeam,
)

pytestmark = pytest.mark.integration

_KEPT_ID = 778000111
_REMOVED_ID = 778000222
_PROOF_URL = "https://utfs.io/f/removed-racer-proof.webp"


async def _seed_finished_event(engine: AsyncEngine) -> dict[str, int]:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        await session.execute(
            sa.update(TileRaceEvent)
            .where(TileRaceEvent.is_active.is_(True))
            .values(is_active=False)
        )
        event = TileRaceEvent(
            name="Recap Test",
            is_active=False,
            is_finished=True,
            fog_of_war=True,
            cells=[
                {"cell_x": 0, "cell_y": 0, "path_position": 1},
                {"cell_x": 1, "cell_y": 0, "path_position": 2},
                {"cell_x": 2, "cell_y": 0, "path_position": None},
            ],
            discord_category_id=987654,
            starts_at=now - timedelta(days=3),
            ends_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        team = TileRaceTeam(
            event_id=event.id,
            name="Reds",
            slug="reds",
            icon_type="npc",
            icon_url="",
            color="#ef4444",
            position=2,
            furthest_position=0,
            discord_role_id=123456,
            updated_at=now,
        )
        session.add(team)
        await session.flush()
        session.add(
            TileRaceSignup(
                event_id=event.id,
                discord_user_id=_KEPT_ID,
                team_id=team.id,
                rsn="kept",
                ranking_score=500,
                is_captain=True,
                signed_up_at=now,
            )
        )
        session.add_all(
            [
                TileRaceRoll(
                    event_id=event.id,
                    team_id=team.id,
                    dice=[4],
                    roll=4,
                    new_position=2,
                    rolled_by=_KEPT_ID,
                    rolled_at=now,
                ),
                TileRaceCompletion(
                    event_id=event.id,
                    team_id=team.id,
                    path_position=1,
                    status="approved",
                    completed_by=_KEPT_ID,
                    completed_at=now,
                ),
            ]
        )
        for author, position, status in (
            (_KEPT_ID, 1, "approved"),
            (_KEPT_ID, 2, "pending"),
            (_REMOVED_ID, 2, "approved"),
        ):
            session.add(
                TileRaceSubmission(
                    event_id=event.id,
                    team_id=team.id,
                    path_position=position,
                    leaf_key=f"text:{author}{position}",
                    leaf_label="Proof",
                    discord_user_id=author,
                    player_rsn="kept" if author == _KEPT_ID else "gone",
                    proof_urls=[_PROOF_URL],
                    discord_thread_id=555000111,
                    status=status,
                    review_notes="looks fine",
                    submitted_at=now,
                    created_at=now,
                )
            )
        ids = {"event_id": event.id, "team_id": team.id}
        await session.commit()
        return ids


async def test_anonymous_recap_drops_removed_racers_and_private_state(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    ids = await _seed_finished_event(seed_engine)

    resp = await anon_client.get(f"/tilerace/events/{ids['event_id']}/recap")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert _PROOF_URL not in resp.text, "a proof URL reached the wire"
    assert "looks fine" not in resp.text, "a review note reached the wire"
    assert "987654" not in resp.text, "a Discord id reached the wire"
    assert str(_REMOVED_ID) not in resp.text, "a removed racer's id reached the wire"
    assert not [k for k in body["event"] if k.startswith("discord_")]

    totals = body["totals"]
    assert totals["submitted"] == 2, "the removed racer's proof was counted"
    assert totals["approved"] == 1
    assert totals["unreviewed"] == 1
    assert totals["removed_racers"] == 1
    assert totals["racers"] == 1
    assert totals["tiles_cleared"] == 1
    assert totals["rolls"] == 1

    team = body["teams"][0]
    assert team["position"] == 2
    assert team["tiles_cleared"] == 1
    assert team["roster"] == [
        {
            "rsn": "kept",
            "is_captain": True,
            "approved": 1,
            "rejected": 0,
            "tiles_proved": 1,
        }
    ]
    assert [p["position"] for p in team["position_series"]] == [2]
    assert team["submission_series"][0]["approved"] == 1
    assert body["event"]["path_length"] == 2
    assert body["next_event"] is None


async def test_recap_names_the_event_that_takes_over(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    ids = await _seed_finished_event(seed_engine)
    now = datetime.now(UTC)
    async with AsyncSession(seed_engine) as session:
        session.add(
            TileRaceEvent(
                name="Frostfall",
                is_active=False,
                is_finished=False,
                cells=[],
                starts_at=now + timedelta(days=7),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    resp = await anon_client.get(f"/tilerace/events/{ids['event_id']}/recap")
    assert resp.status_code == 200, resp.text

    nxt = resp.json()["next_event"]
    assert nxt["name"] == "Frostfall"
    assert nxt["is_active"] is False
    assert nxt["starts_at"] is not None
