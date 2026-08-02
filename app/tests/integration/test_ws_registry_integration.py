"""The connection census, against a real Valkey.

Asserted here rather than against a fake client on purpose: what is under test
is Valkey's own sorted-set semantics - that `zremrangebyscore` drops entries at
the boundary, that `zscore` is None once pruned, that a guild empties out of the
index. A hand-rolled fake would only assert the fake.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from valkey.asyncio import Valkey

from app.services.connection_manager import ConnectionManager
from app.services.ws_registry import GUILDS_KEY, WsRegistry

pytestmark = pytest.mark.integration

_GUILD = 777001
_OTHER_GUILD = 777002


@pytest.fixture
async def registry(_env: dict[str, str]):
    client = Valkey.from_url(_env["valkey_uri"])
    await client.delete(GUILDS_KEY)
    subject = WsRegistry(client, ConnectionManager())
    try:
        yield subject
    finally:
        for guild in (_GUILD, _OTHER_GUILD):
            await client.delete(f"foundry:ws:conns:{guild}")
        await client.delete(GUILDS_KEY)
        await client.aclose()


async def test_an_added_connection_is_visible_to_any_worker(
    registry: WsRegistry,
) -> None:
    conn_id = uuid4()
    await registry.add(_GUILD, conn_id)

    assert await registry.is_connected(_GUILD, conn_id) is True
    assert await registry.count(_GUILD) == 1


async def test_an_unknown_connection_is_not_connected(registry: WsRegistry) -> None:
    await registry.add(_GUILD, uuid4())
    assert await registry.is_connected(_GUILD, uuid4()) is False


async def test_removing_takes_it_out_of_the_census(registry: WsRegistry) -> None:
    conn_id = uuid4()
    await registry.add(_GUILD, conn_id)
    await registry.remove(_GUILD, conn_id)

    assert await registry.is_connected(_GUILD, conn_id) is False
    assert await registry.count(_GUILD) == 0


async def test_a_dead_workers_entries_age_out(_env: dict[str, str]) -> None:
    """No process removes these - the TTL is what stops a crash leaking them."""
    client = Valkey.from_url(_env["valkey_uri"])
    subject = WsRegistry(client, ConnectionManager(), ttl_seconds=1)
    conn_id = uuid4()
    try:
        await subject.add(_GUILD, conn_id)
        assert await subject.count(_GUILD) == 1

        await client.zadd(f"foundry:ws:conns:{_GUILD}", {str(conn_id): time.time() - 5})

        assert await subject.is_connected(_GUILD, conn_id) is False
        assert await subject.count(_GUILD) == 0
    finally:
        await client.delete(f"foundry:ws:conns:{_GUILD}", GUILDS_KEY)
        await client.aclose()


async def test_totals_sum_every_guild_and_forget_the_empty_ones(
    registry: WsRegistry,
) -> None:
    await registry.add(_GUILD, uuid4())
    await registry.add(_GUILD, uuid4())
    emptied = uuid4()
    await registry.add(_OTHER_GUILD, emptied)

    connections, active_guilds = await registry.totals()
    assert (connections, active_guilds) == (3, 2)

    await registry.remove(_OTHER_GUILD, emptied)
    connections, active_guilds = await registry.totals()
    assert (connections, active_guilds) == (2, 1)


async def test_the_heartbeat_keeps_this_workers_connections_alive(
    _env: dict[str, str],
) -> None:
    client = Valkey.from_url(_env["valkey_uri"])
    manager = ConnectionManager()
    subject = WsRegistry(client, manager, ttl_seconds=1)
    try:
        conn_id = manager.connect(None, _GUILD, "key")  # type: ignore[arg-type]
        await subject.add(_GUILD, conn_id)
        await client.zadd(f"foundry:ws:conns:{_GUILD}", {str(conn_id): time.time() - 5})

        await subject._refresh()

        assert await subject.is_connected(_GUILD, conn_id) is True
    finally:
        await client.delete(f"foundry:ws:conns:{_GUILD}", GUILDS_KEY)
        await client.aclose()
