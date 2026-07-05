"""Base async HTTP request handler with shared-client context manager support."""

from __future__ import annotations

from typing import Any, ClassVar, Self

import httpx


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
        if self._client is not None:
            kw: dict[str, Any] = {"params": params}
            if extra_headers:
                kw["headers"] = extra_headers
            return await self._client.get(url, **kw)
        headers = {**self.default_headers, **(extra_headers or {})}
        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            return await client.get(url, params=params)

    async def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            return await self._client.post(url, **kw)
        headers = {**self.default_headers, **(extra_headers or {})}
        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            return await client.post(url, json=json)

    async def put(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            return await self._client.put(url, **kw)
        headers = {**self.default_headers, **(extra_headers or {})}
        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            return await client.put(url, json=json)

    async def delete(
        self,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self.base_url.rstrip("/") + path
        if self._client is not None:
            kw: dict[str, Any] = {"json": json}
            if extra_headers:
                kw["headers"] = extra_headers
            return await self._client.request("DELETE", url, **kw)
        headers = {**self.default_headers, **(extra_headers or {})}
        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            return await client.request("DELETE", url, json=json)
