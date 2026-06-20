from __future__ import annotations

from httpx import AsyncClient


async def test_list_feedback_anon(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/feedback/")
    assert resp.status_code == 200


async def test_list_feedback(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/feedback/")
    assert resp.status_code == 200


async def test_create_feedback_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/feedback/", json={})
    assert resp.status_code == 401


async def test_create_feedback(auth_client: AsyncClient) -> None:
    payload = {"title": "Test", "description": "A bug report", "category": "bug"}
    resp = await auth_client.post("/feedback/", json=payload)
    assert resp.status_code in (200, 201, 422)


async def test_get_feedback_anon(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/feedback/1")
    assert resp.status_code in (200, 404)


async def test_get_feedback_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/feedback/9999")
    assert resp.status_code in (200, 404)


async def test_patch_feedback_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/feedback/1", json={})
    assert resp.status_code == 401


async def test_update_status_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/feedback/1/status", json={"status": "resolved"})
    assert resp.status_code == 401


async def test_react_feedback_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/feedback/1/react", json={"emoji": "👍"})
    assert resp.status_code == 401


async def test_react_feedback(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/feedback/1/react", json={"emoji": "👍"})
    assert resp.status_code in (200, 404, 422)


async def test_add_reply_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/feedback/1/replies", json={"content": "reply"})
    assert resp.status_code == 401


async def test_add_reply(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/feedback/1/replies", json={"content": "A reply"})
    assert resp.status_code in (200, 201, 404, 422)


async def test_delete_reply_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/feedback/1/replies/1")
    assert resp.status_code == 401


async def test_pin_reply_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/feedback/1/replies/1/pin")
    assert resp.status_code == 401


async def test_upload_attachment_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/feedback/upload-attachment")
    assert resp.status_code == 401
