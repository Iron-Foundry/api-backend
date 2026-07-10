"""Shared fixtures for api-backend endpoint tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import (
    get_current_user,
    get_optional_user,
    get_session,
    get_valkey,
    verify_metrics_key,
)
from app.routers import (
    assets,
    auth,
    badges,
    ccdispatch,
    clan,
    config,
    content,
    discord as discord_router,
    events,
    feedback,
    frenzy,
    ironclad,
    map_tiles,
    members,
    metrics,
    parties,
    ranking,
    role_panels,
    runelite_configs,
    staff,
    surveys,
    ticket_config,
    tilerace,
)
from app.tests._staff_patches import staff_permission_patches
from app.tests._wom import mock_wom_instance as mock_wom_instance  # noqa: F401

TEST_USER: dict = {
    "sub": "111222333444555666",
    "username": "TestUser",
    "avatar": None,
    "exp": 9999999999,
}

_ROUTERS = [
    auth.router,
    assets.router,
    badges.router,
    ccdispatch.router,
    clan.router,
    config.router,
    content.router,
    discord_router.router,
    events.router,
    feedback.router,
    frenzy.router,
    ironclad.router,
    map_tiles.router,
    members.router,
    metrics.router,
    parties.router,
    ranking.router,
    role_panels.router,
    runelite_configs.router,
    staff.router,
    surveys.router,
    ticket_config.router,
    tilerace.router,
]


def _build_app() -> FastAPI:
    app = FastAPI()
    for router in _ROUTERS:
        app.include_router(router)
    ranking_svc = MagicMock()
    ranking_svc.last_run_at = None
    ranking_svc.player_count = 0
    ranking_svc.last_error = None
    ranking_svc.service_active = True
    ranking_svc.is_running = False
    ranking_svc.run = AsyncMock()
    ranking_svc.preview = AsyncMock(return_value=[])
    app.state.ranking_service = ranking_svc
    bulk_gains_svc = MagicMock()
    bulk_gains_svc.fetch_and_store = AsyncMock(return_value=0)
    bulk_gains_svc.list_batches = AsyncMock(return_value=[])
    bulk_gains_svc.get_batch_players = AsyncMock(return_value=[])
    bulk_gains_svc.get_player_gains = AsyncMock(return_value=None)
    bulk_gains_svc.find_batch_for_range = AsyncMock(return_value=None)
    app.state.bulk_gains_service = bulk_gains_svc
    tile_sync_svc = MagicMock()
    tile_sync_svc.is_running = False
    tile_sync_svc.start = AsyncMock(return_value={"started": True, "force": False})
    tile_sync_svc.stop = AsyncMock(return_value={"stopped": False})
    tile_sync_svc.status = AsyncMock(return_value={"running": False})
    tile_sync_svc.cached_count = AsyncMock(return_value=0)
    app.state.tile_sync_service = tile_sync_svc
    app.state.session_factory = MagicMock()
    app.state.valkey = AsyncMock()
    from app.services.tile_events import TileEventBus

    app.state.tile_event_bus = TileEventBus("redis://test", app.state.valkey)

    @app.get("/health")
    async def _health() -> dict:
        return {"status": "ok"}

    return app


_app = _build_app()


@pytest.fixture
def mock_session() -> MagicMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    result.scalar_one.return_value = 0
    result.one_or_none.return_value = None
    result.one.return_value = (0, 0)
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.fetchall.return_value = []
    result.rowcount = 0
    session.execute.return_value = result
    session.scalar_one_or_none.return_value = None
    session.scalar.return_value = 0
    session.get.return_value = None
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = MagicMock()
    session.expunge = MagicMock()
    session.expunge_all = MagicMock()
    return session


@pytest.fixture
def mock_valkey() -> AsyncMock:
    v = AsyncMock()
    v.get.return_value = None
    v.set.return_value = True
    v.hgetall.return_value = {}
    return v


def _base_overrides(session: MagicMock, valkey: AsyncMock) -> dict:
    async def _sess() -> AsyncGenerator:
        yield session

    return {
        get_session: _sess,
        get_valkey: lambda: valkey,
        verify_metrics_key: lambda: None,
    }


@pytest.fixture
async def anon_client(
    mock_session: MagicMock, mock_valkey: AsyncMock
) -> AsyncGenerator:
    _app.dependency_overrides = _base_overrides(mock_session, mock_valkey)
    async with AsyncClient(
        transport=ASGITransport(app=_app),
        base_url="http://test",
        headers={"Authorization": "Bearer invalid.token.here"},
        follow_redirects=True,
    ) as ac:
        yield ac
    _app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(
    mock_session: MagicMock, mock_valkey: AsyncMock
) -> AsyncGenerator:
    overrides = _base_overrides(mock_session, mock_valkey)
    overrides[get_current_user] = lambda: TEST_USER
    overrides[get_optional_user] = lambda: TEST_USER
    _app.dependency_overrides = overrides
    async with AsyncClient(
        transport=ASGITransport(app=_app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac
    _app.dependency_overrides.clear()


@pytest.fixture
async def no_redirect_auth_client(
    mock_session: MagicMock, mock_valkey: AsyncMock
) -> AsyncGenerator:
    overrides = _base_overrides(mock_session, mock_valkey)
    overrides[get_current_user] = lambda: TEST_USER
    overrides[get_optional_user] = lambda: TEST_USER
    _app.dependency_overrides = overrides
    async with AsyncClient(
        transport=ASGITransport(app=_app),
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        yield ac
    _app.dependency_overrides.clear()


@pytest.fixture
async def staff_client(
    mock_session: MagicMock, mock_valkey: AsyncMock
) -> AsyncGenerator:
    overrides = _base_overrides(mock_session, mock_valkey)
    overrides[get_current_user] = lambda: TEST_USER
    overrides[get_optional_user] = lambda: TEST_USER
    _app.dependency_overrides = overrides
    with staff_permission_patches():
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            yield ac
    _app.dependency_overrides.clear()
