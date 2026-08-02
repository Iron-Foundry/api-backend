"""One row per interval, holding the whole cluster's numbers.

Every gunicorn worker runs WebSocketMetricsService. Before the lease each wrote
its own row carrying only its own share, so `connected_clients` under-reported
by up to three times at random and the `service_status` upsert was a race. These
stand two workers up against one Valkey and one database to assert the split is
gone.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from valkey.asyncio import Valkey

from app.services.connection_manager import ConnectionManager
from app.services.websocket_metrics import WebSocketMetricsService
from app.services.ws_registry import GUILDS_KEY, WsRegistry

pytestmark = pytest.mark.integration

_GUILD = 888001
_LOCK_KEY = "foundry:ws:metrics_lock"
_DISPATCHED_KEY = "foundry:ws:dispatched"


@pytest.fixture
async def valkey(_env: dict[str, str]):
    client = Valkey.from_url(_env["valkey_uri"])
    await client.delete(_LOCK_KEY, _DISPATCHED_KEY, GUILDS_KEY)
    await client.delete(f"foundry:ws:conns:{_GUILD}")
    try:
        yield client
    finally:
        await client.delete(_LOCK_KEY, _DISPATCHED_KEY, GUILDS_KEY)
        await client.delete(f"foundry:ws:conns:{_GUILD}")
        await client.aclose()


def _worker(
    valkey: Valkey, engine: AsyncEngine, name: str
) -> tuple[ConnectionManager, WsRegistry, WebSocketMetricsService]:
    manager = ConnectionManager()
    registry = WsRegistry(valkey, manager)
    service = WebSocketMetricsService(
        manager,
        async_sessionmaker(engine, expire_on_commit=False),
        None,
        registry=registry,
        worker_id=name,
    )
    return manager, registry, service


async def _rows(engine: AsyncEngine) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT metrics FROM metric_records WHERE module_name = 'websocket' "
                "ORDER BY recorded_at"
            )
        )
        return [row[0] for row in result.all()]


async def test_only_one_worker_writes_the_interval(
    valkey: Valkey, seed_engine: AsyncEngine, _truncate: None
) -> None:
    _, _, first = _worker(valkey, seed_engine, "gw0")
    _, _, second = _worker(valkey, seed_engine, "gw1")

    await first._flush()
    await second._flush()

    assert len(await _rows(seed_engine)) == 1


async def test_the_row_counts_sockets_held_by_every_worker(
    valkey: Valkey, seed_engine: AsyncEngine, _truncate: None
) -> None:
    manager_a, registry_a, first = _worker(valkey, seed_engine, "gw0")
    manager_b, registry_b, _second = _worker(valkey, seed_engine, "gw1")

    await registry_a.add(_GUILD, manager_a.connect(None, _GUILD, "a"))  # type: ignore[arg-type]
    await registry_b.add(_GUILD, manager_b.connect(None, _GUILD, "b"))  # type: ignore[arg-type]

    await first._flush()

    rows = await _rows(seed_engine)
    assert len(rows) == 1
    # Two sockets, one on each worker - the old code would have reported one.
    assert rows[0]["connected_clients"] == 2
    assert rows[0]["active_guilds"] == 1


async def test_no_dispatch_is_lost_or_double_counted(
    valkey: Valkey, seed_engine: AsyncEngine, _truncate: None
) -> None:
    """Whoever wins the lease, the tallies are conserved across intervals.

    A worker that ticks after the writer carries into the next interval rather
    than being dropped - every worker contributes before it tries to claim.
    """
    manager_a, _, first = _worker(valkey, seed_engine, "gw0")
    manager_b, _, second = _worker(valkey, seed_engine, "gw1")
    manager_a._messages_dispatched = 3
    manager_b._messages_dispatched = 4

    await first._flush()
    await second._flush()
    await valkey.delete(_LOCK_KEY)  # the lease expires, the next interval opens
    await second._flush()

    totals = [row["messages_dispatched"] for row in await _rows(seed_engine)]
    assert sum(totals) == 7
    assert await valkey.get(_DISPATCHED_KEY) is None
