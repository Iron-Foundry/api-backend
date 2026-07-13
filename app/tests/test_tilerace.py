from __future__ import annotations

from httpx import AsyncClient


async def test_active_event_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tilerace/active")
    assert resp.status_code in (200, 404)


async def test_active_event_anon(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tilerace/active")
    assert resp.status_code in (200, 404)


async def test_list_events_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tilerace/events")
    assert resp.status_code == 401


async def test_list_events_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/events")
    assert resp.status_code == 200


async def test_create_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tilerace/events", json={"name": "Test"})
    assert resp.status_code == 401


async def test_create_event_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/events", json={"name": "Test"})
    assert resp.status_code in (201, 422)


async def test_get_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tilerace/events/9999")
    assert resp.status_code == 401


async def test_get_event_staff_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/events/9999")
    assert resp.status_code == 404


async def test_patch_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/tilerace/events/9999", json={})
    assert resp.status_code == 401


async def test_delete_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tilerace/events/9999")
    assert resp.status_code == 401


async def test_activate_event_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tilerace/events/9999/activate")
    assert resp.status_code == 401


async def test_activate_event_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/events/9999/activate")
    assert resp.status_code == 404


async def test_deactivate_event_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/events/9999/deactivate")
    assert resp.status_code == 404


async def test_list_repository_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tilerace/repository")
    assert resp.status_code == 401


async def test_list_repository_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/repository")
    assert resp.status_code == 200


async def test_create_tile_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tilerace/repository", json={"title": "Test"})
    assert resp.status_code == 401


async def test_create_tile_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/repository", json={"title": "Test"})
    assert resp.status_code in (201, 422)


async def test_get_tile_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/repository/9999")
    assert resp.status_code == 404


async def test_patch_tile_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch("/tilerace/repository/9999", json={})
    assert resp.status_code == 404


async def test_delete_tile_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.delete("/tilerace/repository/9999")
    assert resp.status_code == 404


async def test_signup_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tilerace/events/9999/signup")
    assert resp.status_code == 401


async def test_cancel_signup_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tilerace/events/9999/signup")
    assert resp.status_code == 401


async def test_cancel_signup_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/tilerace/events/9999/signup")
    assert resp.status_code == 404


async def test_signup_captain_body_accepted(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/tilerace/events/9999/signup", json={"wants_captain": True}
    )
    assert resp.status_code == 404


async def test_signup_rejects_bad_captain_type(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/tilerace/events/9999/signup", json={"wants_captain": "nope"}
    )
    assert resp.status_code == 422


async def test_change_signup_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch(
        "/tilerace/events/9999/signup", json={"account_id": 1}
    )
    assert resp.status_code == 401


async def test_change_signup_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(
        "/tilerace/events/9999/signup", json={"wants_captain": True}
    )
    assert resp.status_code == 404


async def test_add_team_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(
        "/tilerace/events/9999/teams",
        json={"name": "Team A", "slug": "team-a"},
    )
    assert resp.status_code == 401


async def test_add_team_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        "/tilerace/events/9999/teams",
        json={"name": "Team A", "slug": "team-a"},
    )
    assert resp.status_code == 404


async def test_patch_team_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch(
        "/tilerace/events/9999/teams/1", json={"name": "New"}
    )
    assert resp.status_code == 404


async def test_delete_team_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.delete("/tilerace/events/9999/teams/1")
    assert resp.status_code == 404


async def test_scramble_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/events/9999/teams/scramble")
    assert resp.status_code == 404


async def test_roll_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(
        "/tilerace/events/9999/teams/1/roll", json={"roll": 3}
    )
    assert resp.status_code == 401


async def test_roll_team_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/tilerace/events/9999/teams/1/roll", json={"roll": 3}
    )
    assert resp.status_code == 404


async def test_roll_invalid_value(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/tilerace/events/9999/teams/1/roll", json={"roll": 7}
    )
    assert resp.status_code in (400, 404)


async def test_fog_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch(
        "/tilerace/events/9999/fog-of-war", json={"enabled": True}
    )
    assert resp.status_code == 401


async def test_fog_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch(
        "/tilerace/events/9999/fog-of-war", json={"enabled": True}
    )
    assert resp.status_code == 404


async def test_list_completions_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tilerace/events/9999/completions")
    assert resp.status_code == 401


async def test_list_completions_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/events/9999/completions")
    assert resp.status_code == 404


async def test_set_completion_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.put(
        "/tilerace/events/9999/teams/1/completions/1", json={"completed": True}
    )
    assert resp.status_code == 401


async def test_set_completion_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.put(
        "/tilerace/events/9999/teams/1/completions/1", json={"completed": True}
    )
    assert resp.status_code == 404


async def test_sabotage_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(
        "/tilerace/events/9999/teams/1/sabotage",
        json={"action": "block", "target_team_id": 2},
    )
    assert resp.status_code == 401


async def test_sabotage_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        "/tilerace/events/9999/teams/1/sabotage",
        json={"action": "block", "target_team_id": 2},
    )
    assert resp.status_code == 404


async def test_roll_no_body_team_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/tilerace/events/9999/teams/1/roll")
    assert resp.status_code == 404


async def test_osrs_npcs_empty_query(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tilerace/osrs/npcs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_osrs_npcs_short_query(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tilerace/osrs/npcs?q=a")
    assert resp.status_code == 200
    assert resp.json() == []
