"""Fetch one OSRSClans API query, and cache each answer in Valkey.

OSRSClans sends `Cache-Control: public, max-age=3600` on its data and image
routes, so a cached answer stays current for an hour. One query is one request;
a caller must not fetch per row. Identical queries in flight in one worker share
one request, and a failure pauses all calls (`cooldown`).
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from string import Formatter
from typing import Any, ClassVar, Protocol
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from valkey.asyncio import Valkey

from app.services.osrsclans.cooldown import (
    DEFAULT_COOLDOWN_SECONDS,
    cooldown_for,
    raise_if_cooling_down,
    start_cooldown,
)

OSRSCLANS_API_URL = "https://osrsclans.cc/api/v1"
CACHE_TTL_SECONDS = 3600
# Change the prefix when a cached model gains a required field: an older copy
# fails validation until it expires.
_CACHE_PREFIX = "osrsclans:2:"
_HEADERS = {"User-Agent": "The Foundry Project - clan event tracker"}
_TIMEOUT_SECONDS = 10.0

_transport: httpx.AsyncBaseTransport | None = None
_in_flight: dict[str, asyncio.Task[Any]] = {}


class OsrsClansError(Exception):
    """OSRSClans did not answer the query. `cooldown` is the pause it calls for."""

    def __init__(self, message: str, cooldown: int | None = None) -> None:
        super().__init__(message)
        self.cooldown = cooldown


class OsrsClansNotFoundError(OsrsClansError):
    """OSRSClans answered 404: the thing asked for does not exist."""


class OsrsClansAsk(Protocol):
    """A frozen dataclass of one query: its route and its filters."""

    path: ClassVar[str]
    __dataclass_fields__: ClassVar[dict[str, Any]]


def _path_fields(ask: OsrsClansAsk) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(ask.path) if name}


def request_path(ask: OsrsClansAsk) -> str:
    """Return the route of an ask, with its `{field}` path segments filled in."""
    return ask.path.format(**asdict(ask))


def query_params(ask: OsrsClansAsk) -> dict[str, Any]:
    """Return the OSRSClans query string of an ask, without the unset filters."""
    in_path = _path_fields(ask)
    return {
        to_camel(k): v
        for k, v in asdict(ask).items()
        if v is not None and k not in in_path
    }


def cache_key(ask: OsrsClansAsk) -> str:
    """Return the Valkey key of one query, the same for the same filters."""
    query = urlencode(sorted(query_params(ask).items()))
    return f"{_CACHE_PREFIX}{request_path(ask)}?{query}"


async def _get(path: str, params: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        base_url=OSRSCLANS_API_URL,
        headers=_HEADERS,
        timeout=_TIMEOUT_SECONDS,
        transport=_transport,
    ) as client:
        try:
            resp = await client.get(path, params=params)
        except httpx.RequestError as exc:
            raise OsrsClansError(
                "OSRSClans is not reachable", DEFAULT_COOLDOWN_SECONDS
            ) from exc
    if resp.status_code == 404:
        raise OsrsClansNotFoundError(f"OSRSClans answered 404 for {path}")
    if resp.status_code != 200:
        raise OsrsClansError(
            f"OSRSClans answered {resp.status_code}", cooldown_for(resp)
        )
    return resp


async def _get_or_cool(
    valkey: Valkey, path: str, params: dict[str, Any]
) -> httpx.Response:
    try:
        return await _get(path, params)
    except OsrsClansError as exc:
        if exc.cooldown:
            await start_cooldown(valkey, exc.cooldown)
        raise


def _forget(key: str, task: asyncio.Task[Any]) -> None:
    if _in_flight.get(key) is task:
        del _in_flight[key]
    if not task.cancelled():
        task.exception()


async def guarded_get(
    valkey: Valkey, key: str, path: str, params: dict[str, Any]
) -> httpx.Response:
    """Return one OSRSClans answer, shared by all callers of the same `key` in flight.

    Raises `OsrsClansCoolingDownError` without a request while a pause runs. A
    timeout, a 429 or a 5xx starts a pause. The sharing holds in one worker.
    """
    await raise_if_cooling_down(valkey)
    task = _in_flight.get(key)
    if task is None:
        task = asyncio.create_task(_get_or_cool(valkey, path, params))
        _in_flight[key] = task
        task.add_done_callback(lambda done: _forget(key, done))
    return await asyncio.shield(task)


async def cached_page[M: BaseModel](
    valkey: Valkey, ask: OsrsClansAsk, model: type[M]
) -> M:
    """Return the answer of one query as `model`, from the cache when a copy is current."""
    key = cache_key(ask)
    cached = await valkey.get(key)
    if cached:
        return model.model_validate_json(cached)
    resp = await guarded_get(valkey, key, request_path(ask), query_params(ask))
    page = model.model_validate(resp.json())
    await valkey.set(key, page.model_dump_json(), ex=CACHE_TTL_SECONDS)
    return page
