"""Shared fixtures for api-backend endpoint tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from httpx import ASGITransport, AsyncClient

from app.dependencies import (
    get_current_user,
    get_optional_user,
    get_session,
    get_valkey,
    verify_metrics_key,
)
from app.docs import (
    DESCRIPTION,
    SERVERS,
    TAGS_METADATA,
    install_openapi_customization,
    render_reference,
)
from app.routers import (
    assets,
    auth,
    badges,
    ccdispatch,
    clan,
    config,
    content,
    events,
    feedback,
    frenzy,
    members,
    meta,
    metrics,
    music,
    osrs_cache,
    parties,
    ranking,
    reference,
    role_panels,
    runelite_configs,
    staff,
    surveys,
    ticket_config,
    tilerace,
)
from app.routers import (
    discord as discord_router,
)
from app.tests._staff_patches import staff_permission_patches
from app.tests._wom import mock_wom_instance as mock_wom_instance
from app.version import VERSION

TEST_USER: dict[str, Any] = {
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
    members.router,
    meta.router,
    metrics.router,
    music.router,
    osrs_cache.router,
    parties.router,
    ranking.router,
    reference.router,
    role_panels.router,
    runelite_configs.router,
    staff.router,
    surveys.router,
    ticket_config.router,
    tilerace.router,
]


def _build_app() -> FastAPI:
    app = FastAPI(
        title="The Foundry API",
        version=VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        servers=SERVERS,
        docs_url=None,
        redoc_url=None,
    )
    install_openapi_customization(app)
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
    app.state.session_factory = MagicMock()
    app.state.valkey = AsyncMock()
    ws_registry = AsyncMock()
    ws_registry.is_connected = AsyncMock(return_value=True)
    ws_registry.count = AsyncMock(return_value=0)
    ws_registry.totals = AsyncMock(return_value=(0, 0))
    app.state.ws_registry = ws_registry

    @app.get("/docs", include_in_schema=False)
    async def _scalar_docs() -> HTMLResponse:
        return render_reference(app.openapi_url or "/openapi.json", app.title)

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


def _base_overrides(
    session: MagicMock, valkey: AsyncMock
) -> dict[Any, Callable[..., Any]]:
    async def _sess() -> AsyncGenerator[MagicMock]:
        yield session

    return {
        get_session: _sess,
        get_valkey: lambda: valkey,
        verify_metrics_key: lambda: None,
    }


@pytest.fixture
async def anon_client(
    mock_session: MagicMock, mock_valkey: AsyncMock
) -> AsyncGenerator[AsyncClient]:
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
) -> AsyncGenerator[AsyncClient]:
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
) -> AsyncGenerator[AsyncClient]:
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
) -> AsyncGenerator[AsyncClient]:
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
