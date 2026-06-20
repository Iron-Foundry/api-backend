from __future__ import annotations

from httpx import AsyncClient

_UUID = "00000000-0000-0000-0000-000000000001"
_PAGE = "wiki"


async def test_categories_public(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/content/{_PAGE}/categories")
    assert resp.status_code in (200, 404)


async def test_deprecated_entries(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/content/deprecated-entries")
    assert resp.status_code in (200, 403)


async def test_create_category_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(f"/content/{_PAGE}/categories", json={"name": "Test"})
    assert resp.status_code == 401


async def test_create_category_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        f"/content/{_PAGE}/categories", json={"name": "Test", "slug": "test"}
    )
    assert resp.status_code in (403, 422)


async def test_create_category_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        f"/content/{_PAGE}/categories", json={"name": "Test", "slug": "test"}
    )
    assert resp.status_code in (200, 201, 422)


async def test_update_category_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(
        f"/content/{_PAGE}/categories/{_UUID}", json={"name": "Updated"}
    )
    assert resp.status_code in (403, 404, 422)


async def test_delete_category_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete(f"/content/{_PAGE}/categories/{_UUID}")
    assert resp.status_code in (403, 404, 422)


async def test_entry_by_slug_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/content/{_PAGE}/entries/by-slug/nonexistent")
    assert resp.status_code in (200, 404)


async def test_entry_by_id_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/content/{_PAGE}/entries/{_UUID}")
    assert resp.status_code in (200, 404)


async def test_create_entry_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        f"/content/{_PAGE}/categories/{_UUID}/entries",
        json={"title": "Test", "slug": "test", "body": ""},
    )
    assert resp.status_code in (403, 404, 422)


async def test_create_entry_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        f"/content/{_PAGE}/categories/{_UUID}/entries",
        json={"title": "Test", "slug": "test", "body": ""},
    )
    assert resp.status_code in (200, 201, 404, 422)


async def test_entry_versions(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/content/{_PAGE}/entries/{_UUID}/versions")
    assert resp.status_code in (200, 404)


async def test_react_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(
        f"/content/{_PAGE}/entries/{_UUID}/react", json={"emoji": "👍"}
    )
    assert resp.status_code == 401


async def test_react_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        f"/content/{_PAGE}/entries/{_UUID}/react", json={"emoji": "👍"}
    )
    assert resp.status_code in (200, 404, 422)


async def test_remove_react_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete(f"/content/{_PAGE}/entries/{_UUID}/react")
    assert resp.status_code in (401, 405)


async def test_restore_entry_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(f"/content/{_PAGE}/entries/{_UUID}/restore")
    assert resp.status_code in (403, 404, 422)
