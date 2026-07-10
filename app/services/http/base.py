"""Base async HTTP request handler with shared-client context manager support."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, ClassVar, Self
from urllib.parse import urlparse

import httpx

from app.services.outbound_metrics import _collector as _outbound_collector


@lru_cache(maxsize=None)
def _extract_host(base_url: str) -> str:
    return urlparse(base_url).netloc


class BaseRequestHandler:
    base_url: ClassVar[str] = ""
    default_headers: dict[str, str] = {}
    default_timeout: ClassVar[float] = 30.0

    def __init__(self, *, timeout: float | None = None) -> None:
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout if timeout is not None else self.default_timeout

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            headers=dict(self.default_headers),
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        path: str,
        *,
        params: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET request. Uses shared client if inside context manager, else per-call client."""
        url = self.base_url.rstrip("/") + path
        t0 = time.monotonic()
        if self._client is not None:
            kw: dict[str, Any] = {"params": params}
            if extra_headers:
                kw["headers"] = extra_headers
            response = await self._client.get(url, **kw)
        else:
            headers = {**self.default_headers, **(extra_headers or {})}
            async with httpx.AsyncClient(
                headers=headers, timeout=self._timeout
            ) as client:
                response = await client.get(url, params=params)
        _outbound_collector.record(
            _extract_host(self.base_url),
            "GET",
            path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
        )
        return response

    async def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        t0 = time.monotonic()
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            response = await self._client.post(url, **kw)
        else:
            headers = {**self.default_headers, **(extra_headers or {})}
            async with httpx.AsyncClient(
                headers=headers, timeout=self._timeout
            ) as client:
                response = await client.post(url, json=json)
        _outbound_collector.record(
            _extract_host(self.base_url),
            "POST",
            path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
        )
        return response

    async def put(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        t0 = time.monotonic()
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            response = await self._client.put(url, **kw)
        else:
            headers = {**self.default_headers, **(extra_headers or {})}
            async with httpx.AsyncClient(
                headers=headers, timeout=self._timeout
            ) as client:
                response = await client.put(url, json=json)
        _outbound_collector.record(
            _extract_host(self.base_url),
            "PUT",
            path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
        )
        return response

    async def delete(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        t0 = time.monotonic()
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            response = await self._client.request("DELETE", url, **kw)
        else:
            headers = {**self.default_headers, **(extra_headers or {})}
            async with httpx.AsyncClient(
                headers=headers, timeout=self._timeout
            ) as client:
                response = await client.request("DELETE", url, json=json)
        _outbound_collector.record(
            _extract_host(self.base_url),
            "DELETE",
            path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
        )
        return response
