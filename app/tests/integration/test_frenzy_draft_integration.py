"""A frenzy captain draft against the real database and Valkey."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from valkey.asyncio import Valkey

from app.services.frenzy_draft_live import DRAFT_CHANNEL
from app.tests.integration._frenzy_draft_seed import rosters, seed_event, seed_picking

pytestmark = pytest.mark.integration


async def _drawn_and_started(
    staff: AsyncClient, event_id: int, ids: dict[str, int]
) -> list[str]:
    """Top Picks with one pick each; returns the captains in drawn order."""
    base = f"/frenzy/events/{event_id}/draft"
    body = {
        "mode": "top_picks",
        "top_picks": 1,
        "captain_signup_ids": [ids["Cap A"], ids["Cap B"]],
    }
    assert (await staff.put(base, json=body)).status_code == 200
    drawn = await staff.post(f"{base}/draw")
    assert drawn.status_code == 200, drawn.text
    assert (await staff.post(f"{base}/start")).status_code == 200
    return [t["name"] for t in drawn.json()["teams"]]


async def _pick_and_hear(
    staff: AsyncClient, path: str, body: dict[str, int]
) -> dict[str, int]:
    """Make a pick and return the notice it publishes on the draft channel."""
    valkey = Valkey.from_url(os.environ["VALKEY_URI"])
    try:
        async with valkey.pubsub() as pubsub:
            await pubsub.subscribe(DRAFT_CHANNEL)
            await pubsub.get_message(timeout=5)
            assert (await staff.post(path, json=body)).status_code == 200
            async with asyncio.timeout(10):
                while (msg := await pubsub.get_message(timeout=1)) is None:
                    pass
    finally:
        await valkey.aclose()
    return json.loads(msg["data"])


async def test_top_picks_then_snake_hands_out_rest(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, ids = await seed_event(seed_engine)
    first, second = await _drawn_and_started(staff_client, event_id, ids)
    picks = f"/frenzy/events/{event_id}/draft/picks"
    one = {"signup_id": ids["P6"], "pick_number": 1}
    assert await _pick_and_hear(staff_client, picks, one) == {"event_id": event_id}

    two = {"signup_id": ids["P1"], "pick_number": 2}
    done = (await staff_client.post(picks, json=two)).json()

    assert done["state"] == "complete"
    assert done["pool"] == []
    assert await rosters(seed_engine, event_id) == {
        first: [first, "P6", "P3", "P4"],
        second: [second, "P1", "P2", "P5"],
    }
    kinds = {m["rsn"]: m["pick_kind"] for t in done["teams"] for m in t["members"]}
    assert kinds == {"P6": "drafted", "P1": "drafted"} | dict.fromkeys(
        ["P2", "P3", "P4", "P5"], "auto"
    )
    zones = {m["rsn"]: m["timezone"] for t in done["teams"] for m in t["members"]}
    assert zones["P1"] == "Asia/Kolkata"
    assert zones["P2"] is None

    moves = f"/frenzy/events/{event_id}/draft/moves"
    second_id = done["teams"][1]["team_id"]
    moved = await staff_client.post(
        moves, json={"signup_id": ids["P3"], "team_id": second_id}
    )
    assert moved.status_code == 200, moved.text
    assert "P3" in (await rosters(seed_engine, event_id))[second]
    captain = {"signup_id": ids[first], "team_id": second_id}
    assert (await staff_client.post(moves, json=captain)).status_code == 409

    reset = await staff_client.delete(f"/frenzy/events/{event_id}/draft")
    assert reset.status_code == 204
    assert await rosters(seed_engine, event_id) == {}


@pytest.mark.parametrize(
    ("rsn", "pick_number", "code"),
    [("P1", 2, 409), ("Cap A", 1, 422)],
)
async def test_pick_refusals(
    staff_client: AsyncClient,
    seed_engine: AsyncEngine,
    rsn: str,
    pick_number: int,
    code: int,
) -> None:
    event_id, ids = await seed_event(seed_engine)
    await _drawn_and_started(staff_client, event_id, ids)
    body = {"signup_id": ids[rsn], "pick_number": pick_number}
    resp = await staff_client.post(f"/frenzy/events/{event_id}/draft/picks", json=body)
    assert resp.status_code == code, resp.text


async def test_only_the_captain_on_turn_picks(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, ids = await seed_event(seed_engine)
    await seed_picking(seed_engine, event_id, ids)
    resp = await client.post(
        f"/frenzy/events/{event_id}/draft/picks",
        json={"signup_id": ids["P1"], "pick_number": 1},
    )
    assert resp.status_code == 403, resp.text
