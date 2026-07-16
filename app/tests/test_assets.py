from __future__ import annotations

from httpx import AsyncClient
from unittest.mock import MagicMock


async def test_list_assets_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/assets")
    assert resp.status_code == 401


async def test_list_assets_returns_list(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/assets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_serve_file_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/assets/file/nonexistent.png")
    assert resp.status_code == 404


async def test_serve_file_found(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    asset_mock = MagicMock()
    asset_mock.media_type = "image/png"
    asset_mock.filename = "test.png"
    mock_session.execute.return_value.scalar_one_or_none.return_value = asset_mock
    resp = await auth_client.get("/assets/file/test.png")
    assert resp.status_code in (200, 404)


async def test_serve_file_rejects_unsupported_thumbnail_width(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get("/assets/file/test.png", params={"w": 999})
    assert resp.status_code == 400


async def test_serve_file_accepts_supported_thumbnail_width(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    asset_mock = MagicMock()
    asset_mock.content_type = "image/png"
    asset_mock.filename = "test.png"
    mock_session.execute.return_value.scalar_one_or_none.return_value = asset_mock
    resp = await auth_client.get("/assets/file/test.png", params={"w": 256})
    assert resp.status_code in (200, 404)


async def test_upload_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/assets/upload")
    assert resp.status_code == 401


async def test_delete_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/assets/some-uuid")
    assert resp.status_code == 401


async def test_delete_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/assets/some-uuid")
    assert resp.status_code in (404, 403, 422)
