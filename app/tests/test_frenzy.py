from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.routers.frenzy import _osrs_cache


async def test_refresh_osrs_items_uses_cache_service() -> None:
    catalog = [{"item_id": 4151, "name": "Abyssal whip", "members": True}]
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=catalog)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    fake_httpx = MagicMock()
    fake_httpx.AsyncClient = MagicMock(return_value=client)

    valkey = MagicMock()
    valkey.setex = AsyncMock()
    with patch.object(_osrs_cache, "httpx", fake_httpx):
        await _osrs_cache._refresh_osrs_items(valkey)

    assert client.get.call_args.args[0].endswith("/items/catalog")
    stored = json.loads(valkey.setex.call_args.args[2])
    assert stored[0]["id"] == 4151
    assert stored[0]["name"] == "Abyssal whip"
    assert stored[0]["icon_url"].endswith("/osrs-cache/item-icons/4151")
    assert "runescape.wiki" not in stored[0]["icon_url"]


async def test_active_event(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/active")
    assert resp.status_code in (200, 404)


async def test_frenzy_leaderboards(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/leaderboards")
    assert resp.status_code == 200


async def test_active_history(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/active/history")
    assert resp.status_code in (200, 404)


async def test_team_snapshot(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/active/teams/some-team")
    assert resp.status_code in (200, 404)


async def test_team_history(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/active/teams/some-team/history")
    assert resp.status_code in (200, 404)


async def test_osrs_items(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/osrs/items")
    assert resp.status_code == 200


async def test_osrs_bosses(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/osrs/bosses")
    assert resp.status_code == 200


async def test_osrs_activities(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/osrs/activities")
    assert resp.status_code == 200


async def test_templates_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/frenzy/templates")
    assert resp.status_code == 401


async def test_templates_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/frenzy/templates")
    assert resp.status_code == 200


async def test_create_template_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/frenzy/templates", json={"name": "Test"})
    assert resp.status_code in (200, 201, 422)


async def test_events_list_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/frenzy/events")
    assert resp.status_code == 200


async def test_create_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/frenzy/events", json={})
    assert resp.status_code == 401


async def test_create_event_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/frenzy/events", json={"name": "Test Event"})
    assert resp.status_code in (200, 201, 422)


async def test_submissions_public(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/events/9999/submissions")
    assert resp.status_code in (200, 403, 404)


async def test_create_submission_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/frenzy/events/1/submissions", json={})
    assert resp.status_code == 401


async def test_refresh_leaderboards_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/frenzy/leaderboards/refresh")
    assert resp.status_code == 401
