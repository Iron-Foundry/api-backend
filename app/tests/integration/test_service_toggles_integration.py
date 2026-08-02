"""A toggle must reach the workers that did not serve the request.

Same shape as the ccdispatch bug: the registry lives in each worker's memory, so
applying the toggle in place reached one worker of three. The other worker here
is a separate registry with its own ToggleDispatchService - the request has no
way to touch it except through the publish. Collapse it onto the app's own
registry and the test stops proving anything.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.services.toggle_dispatch import ToggleDispatchService

pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("valkey_pubsub")]

_SETTLE_SECONDS = 3.0


def _service(running: bool) -> MagicMock:
    service = MagicMock()
    service.is_running = running
    service.start = AsyncMock()
    service.stop = AsyncMock()
    return service


async def _settle(probe: Any) -> None:
    deadline = asyncio.get_running_loop().time() + _SETTLE_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if probe.await_count:
            return
        await asyncio.sleep(0.05)


@pytest.fixture
async def other_worker(_env: dict[str, str]) -> Any:
    """A second worker: its own registry, its own subscriber, one shared Valkey."""
    registry: dict[str, Any] = {}
    service = ToggleDispatchService(_env["valkey_uri"], registry)
    await service.start()
    await asyncio.sleep(0.5)  # let the subscription land before anything publishes
    try:
        yield registry
    finally:
        await service.stop()


async def test_disabling_stops_the_service_on_another_worker(
    staff_client: AsyncClient, other_worker: dict[str, Any]
) -> None:
    stopped = _service(running=True)
    other_worker["discord_chat"] = stopped

    resp = await staff_client.put(
        "/config/services/toggles/discord_chat", json={"enabled": False}
    )
    assert resp.status_code == 200

    await _settle(stopped.stop)
    stopped.stop.assert_awaited_once()
    stopped.start.assert_not_awaited()


async def test_enabling_starts_the_service_on_another_worker(
    staff_client: AsyncClient, other_worker: dict[str, Any]
) -> None:
    started = _service(running=False)
    other_worker["loot_tables"] = started

    resp = await staff_client.put(
        "/config/services/toggles/loot_tables", json={"enabled": True}
    )
    assert resp.status_code == 200

    await _settle(started.start)
    started.start.assert_awaited_once()
    started.stop.assert_not_awaited()


async def test_the_toggle_survives_a_reread(
    staff_client: AsyncClient, other_worker: dict[str, Any]
) -> None:
    """The database and the running services must agree afterwards."""
    other_worker["music_stats"] = _service(running=True)

    await staff_client.put(
        "/config/services/toggles/music_stats", json={"enabled": False}
    )
    await _settle(other_worker["music_stats"].stop)

    toggles = (await staff_client.get("/config/services/toggles")).json()
    assert toggles["music_stats"] is False
    assert other_worker["music_stats"].stop.await_count == 1


async def test_an_unknown_key_reaches_nobody(
    staff_client: AsyncClient, other_worker: dict[str, Any]
) -> None:
    untouched = _service(running=True)
    other_worker["discord_chat"] = untouched

    resp = await staff_client.put(
        "/config/services/toggles/not_a_service", json={"enabled": False}
    )

    assert resp.status_code == 404
    await asyncio.sleep(0.5)
    untouched.stop.assert_not_awaited()
