"""Toggling a service publishes; it never starts or stops one in place.

Gunicorn runs several workers and each holds its own service registry, so a
toggle applied by the worker that served the PUT reached one worker of three -
the other two kept running the opposite of what the panel showed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.routers.config._helpers import _ALL_SERVICE_KEYS
from app.services.toggle_dispatch import TOGGLE_CHANNEL, apply_toggle


def _published(valkey: AsyncMock) -> dict[str, object]:
    channel, raw = valkey.publish.await_args.args
    assert channel == TOGGLE_CHANNEL
    return json.loads(raw)


async def test_disabling_a_service_is_published_not_applied_here(
    staff_client: AsyncClient,
) -> None:
    app = staff_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()
    service = MagicMock()
    service.is_running = True
    service.stop = AsyncMock()
    app.state.service_registry = {"discord_chat": service}

    resp = await staff_client.put(
        "/config/services/toggles/discord_chat", json={"enabled": False}
    )

    assert resp.status_code == 200
    assert resp.json()["discord_chat"] is False
    service.stop.assert_not_awaited()
    assert _published(app.state.valkey) == {
        "service_key": "discord_chat",
        "enabled": False,
    }


async def test_enabling_a_service_is_published_too(staff_client: AsyncClient) -> None:
    app = staff_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()

    resp = await staff_client.put(
        "/config/services/toggles/loot_tables", json={"enabled": True}
    )

    assert resp.status_code == 200
    assert _published(app.state.valkey) == {
        "service_key": "loot_tables",
        "enabled": True,
    }


async def test_an_unknown_key_is_a_404_and_publishes_nothing(
    staff_client: AsyncClient,
) -> None:
    app = staff_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()

    resp = await staff_client.put(
        "/config/services/toggles/not_a_service", json={"enabled": True}
    )

    assert resp.status_code == 404
    assert "not_a_service" in resp.json()["detail"]
    app.state.valkey.publish.assert_not_awaited()


async def test_toggling_requires_staff(anon_client: AsyncClient) -> None:
    resp = await anon_client.put(
        "/config/services/toggles/discord_chat", json={"enabled": False}
    )
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize("service_key", _ALL_SERVICE_KEYS)
async def test_every_advertised_key_is_accepted(
    staff_client: AsyncClient, service_key: str
) -> None:
    """The panel offers exactly these, so none of them may 404."""
    resp = await staff_client.put(
        f"/config/services/toggles/{service_key}", json={"enabled": True}
    )
    assert resp.status_code == 200


async def test_a_worker_starts_the_service_the_publish_names() -> None:
    service = MagicMock()
    service.is_running = False
    service.start = AsyncMock()

    await apply_toggle(
        {"service_key": "ranking", "enabled": True}, {"ranking": service}
    )

    service.start.assert_awaited_once()


async def test_a_worker_stops_the_service_the_publish_names() -> None:
    service = MagicMock()
    service.is_running = True
    service.stop = AsyncMock()

    await apply_toggle(
        {"service_key": "ranking", "enabled": False}, {"ranking": service}
    )

    service.stop.assert_awaited_once()


async def test_applying_the_same_state_twice_is_a_no_op() -> None:
    """Every worker sees every publish, including re-sends of a settled state."""
    service = MagicMock()
    service.is_running = True
    service.start = AsyncMock()
    service.stop = AsyncMock()

    await apply_toggle(
        {"service_key": "ranking", "enabled": True}, {"ranking": service}
    )

    service.start.assert_not_awaited()
    service.stop.assert_not_awaited()


async def test_a_worker_without_that_service_is_left_alone() -> None:
    """WOM-gated services are absent from some deployments; that is not an error."""
    await apply_toggle({"service_key": "ranking", "enabled": True}, {})
