"""A dispatch must reach the worker holding the socket, not the one serving it.

This is the shape the old code got wrong. `POST /ccdispatch` broadcast straight
into the serving worker's in-process ConnectionManager, so with three gunicorn
workers a dispatch found a given client roughly one time in three. Every test
below e2e ran the app in a single process, where there is only one manager, so
nothing caught it.

The trick here is to give the socket to a manager the request has no access to.
The endpoint is called through the app's own (empty) manager, standing in for
the worker that happened to serve the request; the socket lives on a separate
CcDispatchService, standing in for the worker that actually holds it. Collapse
these onto one manager and the test stops proving anything.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import WebSocket
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.services.cc_dispatch import CcDispatchService
from app.services.connection_manager import ConnectionManager

pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("valkey_pubsub")]

_API_KEY = "worker-split-key"
_GUILD_ID = 555000333
_DISCORD_USER_ID = 900900901
_SETTLE_SECONDS = 2.0


class RecordingSocket:
    """Stands in for a RuneLite client; records what the manager sends it."""

    def __init__(self) -> None:
        self.frames: list[str] = []

    async def send_text(self, message: str) -> None:
        self.frames.append(message)


async def _seed_user(engine: AsyncEngine) -> None:
    from app.db.models import User

    now = datetime.now(UTC)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(
            User(
                discord_user_id=_DISCORD_USER_ID,
                discord_username="worker-split",
                guild_id=_GUILD_ID,
                api_key=_API_KEY,
                key_is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _await_frame(socket: RecordingSocket) -> list[str]:
    deadline = asyncio.get_running_loop().time() + _SETTLE_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if socket.frames:
            return socket.frames
        await asyncio.sleep(0.05)
    return socket.frames


@pytest.fixture
async def other_worker(_env: dict[str, str]) -> Any:
    """A second worker: its own manager, its own subscriber, one shared Valkey."""
    manager = ConnectionManager()
    service = CcDispatchService(_env["valkey_uri"], manager)
    await service.start()
    await asyncio.sleep(0.5)  # let the subscription land before anything publishes
    try:
        yield manager
    finally:
        await service.stop()


async def test_a_dispatch_reaches_a_socket_another_worker_holds(
    client: AsyncClient, seed_engine: AsyncEngine, other_worker: ConnectionManager
) -> None:
    await _seed_user(seed_engine)
    socket = RecordingSocket()
    other_worker.connect(cast(WebSocket, socket), _GUILD_ID, _API_KEY)

    resp = await client.post(
        "/ccdispatch",
        headers={"verification-code": _API_KEY},
        json={"sender": "Zezima", "message": "hello clan", "rank": "Owner"},
    )
    assert resp.status_code == 200

    frames = await _await_frame(socket)
    assert len(frames) == 1
    assert '"sender": "Zezima"' in frames[0]
    assert '"message": "hello clan"' in frames[0]


async def test_a_targeted_dispatch_finds_its_connection_across_workers(
    client: AsyncClient, seed_engine: AsyncEngine, other_worker: ConnectionManager
) -> None:
    await _seed_user(seed_engine)
    socket = RecordingSocket()
    conn_id = other_worker.connect(cast(WebSocket, socket), _GUILD_ID, _API_KEY)
    await client._transport.app.state.ws_registry.add(_GUILD_ID, conn_id)  # type: ignore[attr-defined]

    resp = await client.post(
        f"/ccdispatch?conn_id={conn_id}",
        headers={"verification-code": _API_KEY},
        json={"sender": "Zezima", "message": "just for you"},
    )
    assert resp.status_code == 200
    assert '"message": "just for you"' in (await _await_frame(socket))[0]


async def test_an_unheld_connection_is_refused_before_anything_is_published(
    client: AsyncClient, seed_engine: AsyncEngine, other_worker: ConnectionManager
) -> None:
    await _seed_user(seed_engine)
    socket = RecordingSocket()
    other_worker.connect(cast(WebSocket, socket), _GUILD_ID, _API_KEY)

    resp = await client.post(
        f"/ccdispatch?conn_id={UUID(int=0)}",
        headers={"verification-code": _API_KEY},
        json={"sender": "Zezima", "message": "nobody home"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Client not connected"
    await asyncio.sleep(0.5)
    assert socket.frames == []


async def test_a_long_dispatch_is_chunked_once_on_the_delivering_side(
    client: AsyncClient, seed_engine: AsyncEngine, other_worker: ConnectionManager
) -> None:
    await _seed_user(seed_engine)
    socket = RecordingSocket()
    other_worker.connect(cast(WebSocket, socket), _GUILD_ID, _API_KEY)

    resp = await client.post(
        "/ccdispatch",
        headers={"verification-code": _API_KEY},
        json={"sender": "Zezima", "message": "a drop worth announcing " * 8},
    )
    assert resp.status_code == 200

    frames = await _await_frame(socket)
    assert len(frames) > 1
    assert all('"message_type": "ToClanChat"' in frame for frame in frames)
