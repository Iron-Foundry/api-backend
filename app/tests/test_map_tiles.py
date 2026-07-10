from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


async def test_serve_tile_returns_cached(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    tile = MagicMock()
    tile.data = b"\x89PNG"
    tile.content_type = "image/webp"
    tile.dominant_color = "#3a5c2b"
    tile.has_content = True
    mock_session.get.return_value = tile

    resp = await auth_client.get("/tiles/0/8/35/31")
    assert resp.status_code == 200
    assert resp.headers["x-tile-color"] == "#3a5c2b"
    assert resp.headers["x-tile-has-content"] == "true"


async def test_serve_tile_404_when_upstream_missing(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.get.return_value = None

    with patch(
        "app.routers.map_tiles.serve._fetch_upstream", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = None
        resp = await auth_client.get("/tiles/0/8/35/31")

    assert resp.status_code == 404


async def test_serve_tile_fetches_and_caches(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.get.return_value = None
    fake_webp = b"RIFF\x00\x00\x00\x00WEBP"

    with (
        patch(
            "app.routers.map_tiles.serve._fetch_upstream", new_callable=AsyncMock
        ) as mock_fetch,
        patch("app.routers.map_tiles.serve.process_tile") as mock_process,
        patch("app.routers.map_tiles.serve.tile_region_id", return_value=12889),
    ):
        mock_fetch.return_value = b"\x89PNG\r\n"
        processed = MagicMock()
        processed.data = fake_webp
        processed.content_type = "image/webp"
        processed.dominant_color = "#1a2b3c"
        processed.has_content = True
        processed.size_bytes = len(fake_webp)
        mock_process.return_value = processed

        resp = await auth_client.get("/tiles/0/8/35/31")

    assert resp.status_code == 200
    assert resp.content == fake_webp


async def test_serve_tile_invalid_plane(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tiles/5/8/35/31")
    assert resp.status_code == 422


async def test_serve_tile_invalid_zoom(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tiles/0/3/35/31")
    assert resp.status_code == 422


async def test_sync_status_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tiles/sync/status")
    assert resp.status_code == 401


async def test_sync_status_returns_state(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tiles/sync/status")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        data = resp.json()
        assert "running" in data
        assert "cached" in data


async def test_start_sync_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tiles/sync")
    assert resp.status_code == 401


async def test_delete_tiles_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tiles")
    assert resp.status_code == 401


async def test_stop_sync_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tiles/sync/stop")
    assert resp.status_code == 401


async def test_stop_sync_when_not_running(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/tiles/sync/stop")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        data = resp.json()
        assert "stopped" in data


async def test_delete_region_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tiles/region/12889")
    assert resp.status_code == 401


async def test_delete_region_tiles(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    resp = await auth_client.delete("/tiles/region/12889")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        data = resp.json()
        assert "deleted" in data


async def test_delete_region_invalid_range_anon(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tiles/region/99999")
    assert resp.status_code == 401


async def test_tile_coverage_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tiles/coverage?plane=0&z=8")
    assert resp.status_code == 401


async def test_tile_coverage_returns_structure(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tiles/coverage?plane=0&z=8")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        data = resp.json()
        assert "cols" in data
        assert "rows" in data
        assert "tiles" in data
        assert isinstance(data["tiles"], list)


async def test_event_bus_publishes_to_valkey() -> None:
    from app.services.tile_events import TileEventBus

    valkey = AsyncMock()
    bus = TileEventBus("redis://test", valkey)
    await bus.publish("tile_fetched", plane=0, z=8, x=35, y=31, source="lazy")

    valkey.publish.assert_awaited_once()
    channel, payload = valkey.publish.call_args.args
    assert channel == "foundry:tile_events"
    assert '"type": "tile_fetched"' in payload
    assert '"source": "lazy"' in payload


async def test_sync_start_blocked_when_lock_held() -> None:
    from app.services.tile_sync import TileSyncService

    valkey = AsyncMock()
    valkey.set.return_value = None
    svc = TileSyncService(None, valkey=valkey)
    result = await svc.start()

    assert result == {"started": False, "reason": "already running"}
    assert svc._task is None


async def test_sync_status_reads_valkey_state() -> None:
    from app.services.tile_sync import TileSyncService

    valkey = AsyncMock()
    valkey.get.return_value = b'{"running": true, "processed": 42}'
    svc = TileSyncService(None, valkey=valkey)

    assert await svc.status() == {"running": True, "processed": 42}


async def test_sync_stop_sets_valkey_flag() -> None:
    from app.services.tile_sync import TileSyncService

    valkey = AsyncMock()
    valkey.get.return_value = None
    svc = TileSyncService(None, valkey=valkey)
    result = await svc.stop()

    valkey.set.assert_awaited()
    assert result == {"stopped": False}
