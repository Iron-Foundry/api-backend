"""Real-DB proof that a backwards landing re-opens the ground it took away.

A trap used to move the marker and nothing else: the old completion rows still
read as claimed, so the team rolled straight on again and the Submit button had
no outstanding leaf left to offer. Clearing only the tile they came to rest on
would leave the same free roll waiting on every tile in between, so the whole
span back up to the trap is reset.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
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
_TRAP = {"type": "trap", "dice_count": 2, "dice_sides": 1}


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
    """A three tile board rolling exactly 1, with a trap on tile 3 worth 2."""
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
            name="Setback Test",
            is_active=True,
            dice_count=1,
            dice_sides=1,
            cells=[
                {
                    "path_position": pos,
                    "cell_x": pos,
                    "cell_y": 0,
                    "tile_id": tile_id,
                    "modifiers": [_TRAP] if pos == 3 else [],
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


async def _submit(
    bot_client: AsyncClient, event_id: int, position: int, thread: int
) -> dict[str, Any]:
    resp = await bot_client.post(
        f"/tilerace/events/{event_id}/submissions",
        json={
            "discord_user_id": str(_USER_ID),
            "path_position": position,
            "leaf_keys": _KEYS,
            "proof_urls": ["https://example.test/proof.webp"],
            "discord_thread_id": str(thread),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _roll(client: AsyncClient, event_id: int, team_id: int) -> Any:
    return await client.post(f"/tilerace/events/{event_id}/teams/{team_id}/roll")


async def _walk_into_the_trap(
    bot_client: AsyncClient, client: AsyncClient, event_id: int, team_id: int, seed: int
) -> Any:
    """Clear tiles 1 and 2, then roll onto the trap on tile 3."""
    assert (await _submit(bot_client, event_id, 1, seed))["tile_status"] == "claimed"
    assert (await _roll(client, event_id, team_id)).json()["new_position"] == 2
    assert (await _submit(bot_client, event_id, 2, seed + 1))[
        "tile_status"
    ] == "claimed"
    return await _roll(client, event_id, team_id)


async def test_a_trap_reopens_every_tile_it_threw_the_team_back_over(
    bot_client: AsyncClient,
    client: AsyncClient,
    staff_client: AsyncClient,
    seed_engine: AsyncEngine,
) -> None:
    event_id, team_id = await _seed(seed_engine)

    sprung = await _walk_into_the_trap(bot_client, client, event_id, team_id, 9001)
    assert sprung.status_code == 200, sprung.text
    body = sprung.json()
    assert body["trap"] == {"dice": [1, 1], "total": 2, "from": 3, "to": 1}
    assert body["new_position"] == 1
    assert body["tiles_reset"] == [1, 2], "the whole stretch lost was left completed"

    blocked = await _roll(client, event_id, team_id)
    assert blocked.status_code == 409, "the trap cost the team nothing"
    assert "Submit proof" in blocked.json()["detail"]

    completions = await staff_client.get(f"/tilerace/events/{event_id}/completions")
    assert completions.json() == []

    listed = await staff_client.get(f"/tilerace/events/{event_id}/submissions")
    assert listed.json()["total"] == 0, (
        "proof for the re-opened tiles outlived the reset"
    )


async def test_the_tiles_in_between_gate_the_way_back_up(
    bot_client: AsyncClient, client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, team_id = await _seed(seed_engine)
    await _walk_into_the_trap(bot_client, client, event_id, team_id, 9101)

    context = await bot_client.get(
        "/tilerace/submissions/context", params={"discord_user_id": str(_USER_ID)}
    )
    assert context.status_code == 200, context.text
    reopened = context.json()
    assert reopened["path_position"] == 1
    assert reopened["outstanding"] == len(_KEYS), "nothing left to submit for the tile"
    assert all(not leaf["covered"] for leaf in reopened["leaves"])

    assert (await _submit(bot_client, event_id, 1, 9103))["tile_status"] == "claimed"
    freed = await _roll(client, event_id, team_id)
    assert freed.status_code == 200, freed.text
    assert freed.json()["new_position"] == 2

    regated = await _roll(client, event_id, team_id)
    assert regated.status_code == 409, "tile 2 was walked back over for free"
    assert "Submit proof" in regated.json()["detail"]

    assert (await _submit(bot_client, event_id, 2, 9104))["tile_status"] == "claimed"
    spent = await _roll(client, event_id, team_id)
    assert spent.status_code == 200, spent.text
    assert spent.json()["trap_spent"] == 3, "the trap bit a second time"
    assert spent.json()["new_position"] == 3
    assert "tiles_reset" not in spent.json()
