"""Real-DB lifecycle for the parties router: create -> read -> update -> close."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_party_lifecycle(client: AsyncClient) -> None:
    payload = {"activity": "Chambers of Xeric", "max_size": 4, "vibe": "chill"}
    created = await client.post("/parties/", json=payload)
    assert created.status_code == 201, created.text
    party = created.json()
    pid = party["id"]
    assert party["activity"] == "Chambers of Xeric"
    assert party["status"] != "closed"
    # Creator is auto-added as the sole member/leader.
    assert party["member_count"] == 1
    assert party["leader"]["user_id"] == "111222333444555666"

    listed = await client.get("/parties/")
    assert listed.status_code == 200
    assert any(p["id"] == pid for p in listed.json())

    fetched = await client.get(f"/parties/{pid}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == pid

    updated = await client.patch(
        f"/parties/{pid}", json={"activity": "Theatre of Blood", "max_size": 5}
    )
    assert updated.status_code == 200
    assert updated.json()["activity"] == "Theatre of Blood"
    assert updated.json()["max_size"] == 5

    closed = await client.delete(f"/parties/{pid}")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    # Closed parties drop out of the active list.
    after = await client.get("/parties/")
    assert not any(p["id"] == pid for p in after.json())


async def test_update_party_requires_leader(client: AsyncClient, app: FastAPI) -> None:
    created = await client.post("/parties/", json={"activity": "Nex", "max_size": 8})
    pid = created.json()["id"]

    from app.dependencies import get_current_user

    other = {"sub": "999888777666555444", "username": "Interloper", "exp": 9999999999}
    app.dependency_overrides[get_current_user] = lambda: other
    resp = await client.patch(f"/parties/{pid}", json={"activity": "hijacked"})
    assert resp.status_code == 403
