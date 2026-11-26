"""The pause after OSRSClans fails: until it ends, Foundry sends OSRSClans nothing.

A timeout, a 429, a 502, a 503 or a 504 starts it, for the seconds of `Retry-After` when
OSRSClans sends one. The pause lives in Valkey, so every worker honours it.
Routes answer 503 at once while it runs, so a slow OSRSClans never holds
Foundry's requests open.
"""

from __future__ import annotations

import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from valkey.asyncio import Valkey

COOLDOWN_KEY = "osrsclans:cooldown"
DEFAULT_COOLDOWN_SECONDS = 30
_MAX_COOLDOWN_SECONDS = 300
_OVERLOAD_STATUSES = frozenset({429, 502, 503, 504})


class OsrsClansCoolingDownError(Exception):
    """OSRSClans failed a moment ago; Foundry waits `retry_after` seconds more."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"OSRSClans is unavailable; retry in {retry_after} s")
        self.retry_after = retry_after


def cooldown_for(resp: httpx.Response) -> int | None:
    """Return the pause a failed answer calls for, or None for an answer that needs none.

    Only 429 and the gateway answers (502, 503, 504) pause: they say OSRSClans is
    overloaded or down. A 500 can come from one odd request, and a pause on it
    would let any caller stop all OSRSClans calls.
    """
    if resp.status_code not in _OVERLOAD_STATUSES:
        return None
    header = resp.headers.get("Retry-After", "")
    seconds = int(header) if header.isdigit() else DEFAULT_COOLDOWN_SECONDS
    return max(1, min(seconds, _MAX_COOLDOWN_SECONDS))


async def start_cooldown(
    valkey: Valkey, seconds: int, now: float | None = None
) -> None:
    """Pause all OSRSClans calls for `seconds`."""
    ends = int(now if now is not None else time.time()) + seconds
    await valkey.set(COOLDOWN_KEY, str(ends), ex=seconds)


async def raise_if_cooling_down(valkey: Valkey, now: float | None = None) -> None:
    """Raise `OsrsClansCoolingDownError` while a pause runs."""
    ends = await valkey.get(COOLDOWN_KEY)
    if not ends:
        return
    left = int(ends) - int(now if now is not None else time.time())
    if left > 0:
        raise OsrsClansCoolingDownError(left)


async def _cooling_down_response(_request: Request, exc: Exception) -> JSONResponse:
    retry_after = exc.retry_after if isinstance(exc, OsrsClansCoolingDownError) else 1
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": str(retry_after)},
    )


def install_cooldown_handler(app: FastAPI) -> None:
    """Answer 503 with `Retry-After` on every route while OSRSClans cools down."""
    app.add_exception_handler(OsrsClansCoolingDownError, _cooling_down_response)
