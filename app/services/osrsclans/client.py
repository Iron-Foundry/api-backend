"""Fetch one OSRSClans API query, and cache each answer in Valkey.

OSRSClans sends `Cache-Control: public, max-age=3600` on its data and image
routes, so a cached answer stays current for an hour. One query is one request;
a caller must not fetch per row.
"""

from __future__ import annotations

from dataclasses import asdict
from string import Formatter
from typing import Any, ClassVar, Protocol
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from valkey.asyncio import Valkey

OSRSCLANS_API_URL = "https://osrsclans.cc/api/v1"
CACHE_TTL_SECONDS = 3600
# Change the prefix when a cached model gains a required field: an older copy
# fails validation until it expires.
_CACHE_PREFIX = "osrsclans:2:"
_HEADERS = {"User-Agent": "The Foundry Project - clan event tracker"}
_TIMEOUT_SECONDS = 10.0

_transport: httpx.AsyncBaseTransport | None = None


class OsrsClansError(Exception):
    """OSRSClans did not answer the query."""


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


async def _fetch_json(ask: OsrsClansAsk) -> Any:
    async with httpx.AsyncClient(
        base_url=OSRSCLANS_API_URL,
        headers=_HEADERS,
        timeout=_TIMEOUT_SECONDS,
        transport=_transport,
    ) as client:
        try:
            resp = await client.get(request_path(ask), params=query_params(ask))
        except httpx.RequestError as exc:
            raise OsrsClansError("OSRSClans is not reachable") from exc
    if resp.status_code == 404:
        raise OsrsClansNotFoundError(f"OSRSClans answered 404 for {request_path(ask)}")
    if resp.status_code != 200:
        raise OsrsClansError(f"OSRSClans answered {resp.status_code}")
    return resp.json()


async def cached_page[M: BaseModel](
    valkey: Valkey, ask: OsrsClansAsk, model: type[M]
) -> M:
    """Return the answer of one query as `model`, from the cache when a copy is current."""
    key = cache_key(ask)
    cached = await valkey.get(key)
    if cached:
        return model.model_validate_json(cached)
    page = model.model_validate(await _fetch_json(ask))
    await valkey.set(key, page.model_dump_json(), ex=CACHE_TTL_SECONDS)
    return page
