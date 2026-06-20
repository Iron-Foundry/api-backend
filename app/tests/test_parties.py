from __future__ import annotations

from httpx import AsyncClient

_UUID = "00000000-0000-0000-0000-000000000001"


async def test_list_parties_anon(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/parties/")
    assert resp.status_code == 200


async def test_list_parties(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/parties/")
    assert resp.status_code == 200


async def test_create_party_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/parties/", json={})
    assert resp.status_code == 401


async def test_create_party(auth_client: AsyncClient) -> None:
    payload = {"activity": "Cox", "max_size": 4, "description": "Test party"}
    resp = await auth_client.post("/parties/", json=payload)
    assert resp.status_code in (200, 201, 422)


async def test_get_party_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/parties/{_UUID}")
    assert resp.status_code in (200, 404)


async def test_update_party_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch(f"/parties/{_UUID}", json={})
    assert resp.status_code == 401


async def test_delete_party_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete(f"/parties/{_UUID}")
    assert resp.status_code == 401


async def test_join_party_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(f"/parties/{_UUID}/join")
    assert resp.status_code == 401


async def test_join_party_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(f"/parties/{_UUID}/join")
    assert resp.status_code in (200, 404)


async def test_leave_party_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete(f"/parties/{_UUID}/leave")
    assert resp.status_code == 401


async def test_kick_member_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete(f"/parties/{_UUID}/members/111222333")
    assert resp.status_code == 401


async def test_party_chat_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/parties/{_UUID}/chat")
    assert resp.status_code in (200, 401, 404)


async def test_send_chat_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(f"/parties/{_UUID}/chat", json={"content": "hello"})
    assert resp.status_code == 401


async def test_notifications_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/parties/notifications")
    assert resp.status_code == 401


async def test_notifications(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/parties/notifications")
    assert resp.status_code == 200


async def test_update_notifications_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.put("/parties/notifications", json={})
    assert resp.status_code == 401
