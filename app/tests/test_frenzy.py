from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client as osrsclans_client

_WHIP_PAGE = {
    "items": [
        {"id": 4151, "name": "Abyssal whip", "members": True},
        {"id": 4152, "name": None, "members": True},
    ],
    "total": 2,
    "limit": 30,
    "offset": 0,
}


async def test_item_search_reads_osrsclans_named_items(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_WHIP_PAGE)

    monkeypatch.setattr(osrsclans_client, "_transport", httpx.MockTransport(answer))

    resp = await auth_client.get("/frenzy/osrs/items?q=whip")

    assert resp.status_code == 200, resp.text
    assert resp.json() == [
        {
            "id": 4151,
            "name": "Abyssal whip",
            "icon_url": "https://osrsclans.cc/api/v1/osrs/items/4151.webp",
            "members": True,
        }
    ]
    assert seen[0].url.path == "/api/v1/osrs/items/search"


async def test_active_event(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/active")
    assert resp.status_code in (200, 404)


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
async def test_signup_requires_login(anon_client: AsyncClient, method: str) -> None:
    resp = await getattr(anon_client, method)("/frenzy/events/1/signup")
    assert resp.status_code == 401


async def test_signup_list_needs_frenzy_admin(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/frenzy/events/1/signups")
    assert resp.status_code == 403


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
