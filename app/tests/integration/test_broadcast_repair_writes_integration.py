"""The event repair write path, exercised against a real database."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.broadcast_repair import event_repair
from app.services.broadcast_repair_writes import stored_event, write_repair

pytestmark = pytest.mark.integration

_LOOT = "Kz Grind received a drop: 2 x Spirit seed (280,000 coins)."
_PB = "Kz Grind achieved a new Corp Beast personal best: 1:23.40"
_AT = datetime(2026, 11, 24, 12, 0, 30, tzinfo=UTC)

_SEED_USER = sa.text(
    "INSERT INTO users (discord_user_id, discord_username, rsn, created_at,"
    " updated_at) VALUES (1, 'kz', 'Kz Grind', now(), now())"
)
_SEED_EVENT = sa.text(
    "INSERT INTO events (type, timestamp, player_name, sender, raw_message, data)"
    " VALUES (:type, :at, :player, 'Iron Foundry', :raw, '{}') RETURNING id"
)
_FETCH_EVENT = sa.text(
    "SELECT id, type, player_name, sender, raw_message, data, timestamp"
    " FROM events WHERE id = :id"
)


async def _seed(engine: AsyncEngine, raw: str, *, duplicate: bool = False) -> int:
    """Seed the user and an unknown row, and return the unknown row's id."""
    async with engine.begin() as conn:
        await conn.execute(_SEED_USER)
        if duplicate:
            stored = {"type": "loot", "at": _AT, "player": "Kz Grind", "raw": raw}
            await conn.execute(_SEED_EVENT, stored)
        unknown = {"type": "unknown", "at": _AT, "player": None, "raw": raw}
        return (await conn.execute(_SEED_EVENT, unknown)).scalar_one()


async def _write(engine: AsyncEngine, event_id: int) -> bool:
    async with engine.begin() as conn:
        row = (await conn.execute(_FETCH_EVENT, {"id": event_id})).mappings().one()
        stored = stored_event(row)
        repair = event_repair(stored, stored.raw_message)
        assert repair is not None
        return await write_repair(conn, repair, row["type"], row["timestamp"])


async def _scalar(engine: AsyncEngine, query: str, **params: object) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(sa.text(query), params)).scalar_one()


async def test_loot_repair_credits_owed_value(
    seed_engine: AsyncEngine, _truncate: None
) -> None:
    event_id = await _seed(seed_engine, _LOOT)
    assert await _write(seed_engine, event_id) is False
    loot = await _scalar(seed_engine, "SELECT total_loot_value FROM users")
    stored_type = await _scalar(
        seed_engine, "SELECT type FROM events WHERE id = :id", id=event_id
    )
    assert (loot, stored_type) == (280000, "loot")


async def test_pb_repair_keeps_fractional_seconds(
    seed_engine: AsyncEngine, _truncate: None
) -> None:
    event_id = await _seed(seed_engine, _PB)
    await _write(seed_engine, event_id)
    time = await _scalar(seed_engine, "SELECT time_seconds FROM leaderboards")
    assert time == Decimal("83.400")


async def test_duplicate_repair_deletes_row_uncredited(
    seed_engine: AsyncEngine, _truncate: None
) -> None:
    event_id = await _seed(seed_engine, _LOOT, duplicate=True)
    assert await _write(seed_engine, event_id) is True
    loot = await _scalar(seed_engine, "SELECT total_loot_value FROM users")
    remaining = await _scalar(seed_engine, "SELECT count(*) FROM events")
    assert (loot, remaining) == (0, 1)
