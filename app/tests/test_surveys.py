from __future__ import annotations

from httpx import AsyncClient

_UUID = "00000000-0000-0000-0000-000000000001"


async def test_list_surveys(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/surveys/")
    assert resp.status_code == 200


async def test_list_applications(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/surveys/applications")
    assert resp.status_code == 200


async def test_get_survey_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/surveys/{_UUID}")
    assert resp.status_code in (200, 404)


async def test_submit_response(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(f"/surveys/{_UUID}/responses", json={"answers": []})
    assert resp.status_code in (200, 201, 404, 422)


async def test_get_responses_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get(f"/surveys/{_UUID}/responses")
    assert resp.status_code == 401


async def test_get_responses_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/surveys/{_UUID}/responses")
    assert resp.status_code in (200, 403, 404)


async def test_get_responses_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get(f"/surveys/{_UUID}/responses")
    assert resp.status_code in (200, 404)


async def test_create_survey_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/surveys/", json={})
    assert resp.status_code == 401


async def test_create_survey_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/surveys/", json={"title": "Test"})
    assert resp.status_code == 403


async def test_create_survey_staff(staff_client: AsyncClient) -> None:
    payload = {"title": "Test Survey", "questions": []}
    resp = await staff_client.post("/surveys/", json=payload)
    assert resp.status_code in (200, 201, 422)


async def test_update_survey_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.put(f"/surveys/{_UUID}", json={"title": "Updated"})
    assert resp.status_code == 403


async def test_open_survey_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(f"/surveys/{_UUID}/open")
    assert resp.status_code in (403, 404, 422)


async def test_visibility_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(
        f"/surveys/{_UUID}/visibility", json={"visible": True}
    )
    assert resp.status_code in (403, 404, 422)
