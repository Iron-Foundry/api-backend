from __future__ import annotations

from httpx import AsyncClient


async def test_list_batches_public(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/clan/bulk-gains/batches")
    assert resp.status_code == 200


async def test_list_batches_authenticated(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/bulk-gains/batches")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_batch_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/bulk-gains/batches/9999")
    assert resp.status_code == 404


async def test_get_player_gains_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/bulk-gains/batches/1/players/testplayer")
    assert resp.status_code == 404


async def test_fetch_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/clan/bulk-gains/fetch", json={"period": "week"})
    assert resp.status_code == 401


async def test_fetch_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/clan/bulk-gains/fetch", json={"period": "week"})
    assert resp.status_code == 403


async def test_fetch_staff_missing_params(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/clan/bulk-gains/fetch", json={})
    assert resp.status_code == 422


async def test_fetch_staff_with_period(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/clan/bulk-gains/fetch", json={"period": "week"})
    assert resp.status_code == 201
    body = resp.json()
    assert "players_stored" in body


async def test_parse_bulk_gains_data() -> None:
    from app.services.bulk_gains._parse import parse_bulk_gains_data

    data = [
        {"metric": "overall", "gained": 1000, "start": 100000, "end": 101000},
        {"metric": "attack", "gained": 500, "start": 50000, "end": 50500},
        {"metric": "abyssal_sire", "gained": 5, "start": 10, "end": 15},
        {"metric": "clue_scrolls_all", "gained": 3, "start": 0, "end": 3},
        {"metric": "ehp", "gained": 0.5, "start": 100.0, "end": 100.5},
    ]
    skills, bosses, activities = parse_bulk_gains_data(data)

    assert "overall" in skills
    assert "attack" in skills
    assert "abyssal_sire" in bosses
    assert "clue_scrolls_all" in activities
    assert "ehp" not in skills
    assert "ehp" not in bosses
    assert "ehp" not in activities
    assert skills["overall"] == {"gained": 1000, "start": 100000, "end": 101000}
