"""Real-DB round trip for the submission claim state machine.

Guards the loop the written rules promise teams: a claim unlocks the next roll
without waiting for staff, a rejection sends the team back to the tile it was
proving, and clearing that tile again hands back the point it had reached.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    TileRaceEvent,
    TileRaceSignup,
    TileRaceTeam,
    TileRepositoryTile,
)

pytestmark = pytest.mark.integration

_USER_ID = 111222333444555666  # matches conftest TEST_USER["sub"], so rolls are allowed
_ITEMS = [
    {"item_id": 11832, "quantity": 1, "name": "Bandos chestplate"},
    {"item_id": 11834, "quantity": 1, "name": "Bandos tassets"},
]
_KEYS = ["item:11832:1", "item:11834:1"]


@pytest.fixture
async def bot_client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    """A client that passes the service-key dependency, like discord-server."""
    from app.dependencies import verify_metrics_key

    app.dependency_overrides[verify_metrics_key] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(verify_metrics_key, None)


async def _seed(engine: AsyncEngine) -> tuple[int, int]:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        tile = TileRepositoryTile(
            title="Bandos armour",
            description="",
            items=_ITEMS,
            requirement=None,
            tags=[],
            created_at=now,
            updated_at=now,
        )
        session.add(tile)
        await session.flush()
        tile_id = tile.id

        event = TileRaceEvent(
            name="Submission Test",
            is_active=True,
            dice_count=1,
            dice_sides=1,
            cells=[
                {
                    "path_position": pos,
                    "cell_x": pos,
                    "cell_y": 0,
                    "tile_id": tile_id,
                    "modifiers": [],
                }
                for pos in (1, 2, 3)
            ],
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        event_id = event.id

        team = TileRaceTeam(
            event_id=event_id,
            name="Abyssal Ashes",
            slug="abyssal-ashes",
            position=1,
            updated_at=now,
        )
        session.add(team)
        await session.flush()
        team_id = team.id

        session.add(
            TileRaceSignup(
                event_id=event_id,
                team_id=team_id,
                discord_user_id=_USER_ID,
                rsn="zezima",
                is_captain=True,
                signed_up_at=now,
            )
        )
        await session.commit()
        return event_id, team_id


async def _team_row(engine: AsyncEngine, team_id: int) -> sa.Row[tuple[int, int]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT position, furthest_position FROM tilerace_teams WHERE id = :t"
            ),
            {"t": team_id},
        )
        return result.one()


async def _submit(
    bot_client: AsyncClient, event_id: int, position: int, keys: list[str], thread: int
) -> dict[str, Any]:
    resp = await bot_client.post(
        f"/tilerace/events/{event_id}/submissions",
        json={
            "discord_user_id": str(_USER_ID),
            "path_position": position,
            "leaf_keys": keys,
            "proof_urls": ["https://example.test/proof.webp"],
            "discord_thread_id": str(thread),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_claim_unlocks_the_roll_and_a_rejection_rolls_the_team_back(
    bot_client: AsyncClient, client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, team_id = await _seed(seed_engine)

    context = await bot_client.get(
        "/tilerace/submissions/context",
        params={"discord_user_id": str(_USER_ID)},
    )
    assert context.status_code == 200, context.text
    assert [leaf["key"] for leaf in context.json()["leaves"]] == _KEYS
    assert all(not leaf["covered"] for leaf in context.json()["leaves"])

    partial = await _submit(bot_client, event_id, 1, [_KEYS[0]], 5001)
    assert partial["tile_status"] == "none", "half a tile is not a claim"

    blocked = await client.post(f"/tilerace/events/{event_id}/teams/{team_id}/roll")
    assert blocked.status_code == 409
    assert "Submit proof" in blocked.json()["detail"]

    full = await _submit(bot_client, event_id, 1, [_KEYS[1]], 5002)
    assert full["tile_status"] == "claimed"

    rolled = await client.post(f"/tilerace/events/{event_id}/teams/{team_id}/roll")
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["new_position"] == 2

    rejected = await bot_client.post(
        f"/tilerace/events/{event_id}/submissions/threads/5002/review",
        json={
            "status": "rejected",
            "reviewed_by": "111",
            "review_notes": "Tassets are not in the screenshot.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["tile_status"] == "rejected"

    row = await _team_row(seed_engine, team_id)
    assert row.position == 1, "a rejection sends the team back to the failed tile"
    assert row.furthest_position == 2, "the active point is remembered"

    relocked = await client.post(f"/tilerace/events/{event_id}/teams/{team_id}/roll")
    assert relocked.status_code == 409

    redone = await _submit(bot_client, event_id, 1, [_KEYS[1]], 5003)
    assert redone["tile_status"] == "claimed"

    row = await _team_row(seed_engine, team_id)
    assert row.position == 2, "clearing the tile returns the team to its active point"
    assert row.furthest_position == 0


async def test_approving_every_leaf_marks_the_tile_approved(
    bot_client: AsyncClient, staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, team_id = await _seed(seed_engine)
    await _submit(bot_client, event_id, 1, _KEYS, 6001)

    approved = await bot_client.post(
        f"/tilerace/events/{event_id}/submissions/threads/6001/review",
        json={"status": "approved", "reviewed_by": "111"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["tile_status"] == "approved"

    completions = await staff_client.get(f"/tilerace/events/{event_id}/completions")
    assert completions.status_code == 200
    rows = completions.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "approved"
    assert rows[0]["team_id"] == str(team_id)


async def test_deleting_a_submission_unpicks_the_claim(
    bot_client: AsyncClient, staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, team_id = await _seed(seed_engine)
    created = await _submit(bot_client, event_id, 1, _KEYS, 8001)
    assert created["tile_status"] == "claimed"

    rolled = await staff_client.post(
        f"/tilerace/events/{event_id}/teams/{team_id}/roll"
    )
    assert rolled.status_code == 200, rolled.text

    removed = await staff_client.delete(
        f"/tilerace/events/{event_id}/submissions/{created['ids'][0]}"
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["tile_status"] == "rejected"

    row = await _team_row(seed_engine, team_id)
    assert row.position == 1
    assert row.furthest_position == 2

    listed = await staff_client.get(f"/tilerace/events/{event_id}/submissions")
    assert listed.json()["total"] == 1, "only the deleted row is gone"


async def test_a_submission_for_an_unknown_leaf_is_refused(
    bot_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, _team_id = await _seed(seed_engine)
    resp = await bot_client.post(
        f"/tilerace/events/{event_id}/submissions",
        json={
            "discord_user_id": str(_USER_ID),
            "path_position": 1,
            "leaf_keys": ["item:999:1"],
            "proof_urls": [],
            "discord_thread_id": "7001",
        },
    )
    assert resp.status_code == 400
    assert "Unknown requirement leaves" in resp.json()["detail"]
