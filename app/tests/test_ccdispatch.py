"""The dispatch endpoint publishes; it never delivers on its own.

The sockets are spread across every gunicorn worker and each worker's
ConnectionManager sees only its own, so an endpoint that broadcast directly
reached roughly one client in three. These assert the endpoint hands the message
to Valkey instead, and that a `conn_id` nobody holds is still a 404.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies import verify_clan
from app.services.cc_dispatch import CC_DISPATCH_CHANNEL

_GUILD_ID = 4242
_CLAN = {"guild_id": _GUILD_ID, "discord_user_id": 900, "key": "k"}


@pytest.fixture
def clan_client(auth_client: AsyncClient) -> AsyncClient:
    auth_client._transport.app.dependency_overrides[verify_clan] = lambda: _CLAN  # type: ignore[attr-defined]
    return auth_client


def _published(valkey: AsyncMock) -> dict[str, object]:
    channel, raw = valkey.publish.await_args.args
    assert channel == CC_DISPATCH_CHANNEL
    return json.loads(raw)


async def test_dispatch_publishes_instead_of_broadcasting(
    clan_client: AsyncClient,
) -> None:
    app = clan_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()

    with patch("app.services.connection_manager.connection_manager") as manager:
        resp = await clan_client.post(
            "/ccdispatch",
            json={"sender": "Zezima", "message": "gz on the drop", "rank": "Owner"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    manager.broadcast.assert_not_called()

    body = _published(app.state.valkey)
    assert body["guild_id"] == _GUILD_ID
    assert body["sender"] == "Zezima"
    assert body["rank"] == "Owner"
    assert body["message"] == "gz on the drop"
    assert body["conn_id"] is None


async def test_the_whole_message_crosses_unsplit(clan_client: AsyncClient) -> None:
    """Chunking belongs to the subscriber, so it happens in exactly one place."""
    app = clan_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()
    long_message = "a drop worth announcing " * 8

    resp = await clan_client.post(
        "/ccdispatch", json={"sender": "Zezima", "message": long_message}
    )

    assert resp.status_code == 200
    assert app.state.valkey.publish.await_count == 1
    assert _published(app.state.valkey)["message"] == long_message


async def test_a_targeted_dispatch_names_the_connection(
    clan_client: AsyncClient,
) -> None:
    app = clan_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()
    conn_id = uuid4()

    resp = await clan_client.post(
        f"/ccdispatch?conn_id={conn_id}",
        json={"sender": "Zezima", "message": "just for you"},
    )

    assert resp.status_code == 200
    assert _published(app.state.valkey)["conn_id"] == str(conn_id)


async def test_an_unattached_connection_is_a_404_and_publishes_nothing(
    clan_client: AsyncClient,
) -> None:
    app = clan_client._transport.app  # type: ignore[attr-defined]
    app.state.valkey.publish.reset_mock()
    app.state.ws_registry.is_connected = AsyncMock(return_value=False)
    try:
        resp = await clan_client.post(
            f"/ccdispatch?conn_id={uuid4()}",
            json={"sender": "Zezima", "message": "nobody home"},
        )
    finally:
        app.state.ws_registry.is_connected = AsyncMock(return_value=True)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Client not connected"
    app.state.valkey.publish.assert_not_awaited()


async def test_dispatch_requires_a_clan_key(anon_client: AsyncClient) -> None:
    app = anon_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides.pop(verify_clan, None)
    resp = await anon_client.post(
        "/ccdispatch", json={"sender": "Zezima", "message": "no key"}
    )
    assert resp.status_code == 401
