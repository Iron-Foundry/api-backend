"""Valkey-backed shared state coordinating tile sync across gunicorn workers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valkey.asyncio import Valkey

_LOCK_KEY = "foundry:tile_sync:lock"
_STATE_KEY = "foundry:tile_sync:state"
_STOP_KEY = "foundry:tile_sync:stop"
_TTL = 60


async def acquire_lock(valkey: Valkey, owner: str) -> bool:
    acquired = bool(await valkey.set(_LOCK_KEY, owner, nx=True, ex=_TTL))
    if acquired:
        await valkey.delete(_STOP_KEY)
    return acquired


async def release_lock(valkey: Valkey) -> None:
    await valkey.delete(_LOCK_KEY, _STATE_KEY, _STOP_KEY)


async def write_state(valkey: Valkey, state: dict) -> None:
    await valkey.set(_STATE_KEY, json.dumps(state), ex=_TTL)
    await valkey.expire(_LOCK_KEY, _TTL)


async def read_state(valkey: Valkey) -> dict:
    raw = await valkey.get(_STATE_KEY)
    if not raw:
        return {"running": False}
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


async def request_stop(valkey: Valkey) -> None:
    await valkey.set(_STOP_KEY, "1", ex=_TTL)


async def stop_requested(valkey: Valkey) -> bool:
    return bool(await valkey.get(_STOP_KEY))
