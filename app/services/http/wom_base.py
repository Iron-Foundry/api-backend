"""Shared base declaring the interface that WOM mixin classes depend on."""

from __future__ import annotations

import httpx

from app.services.http.base import BaseRequestHandler
from app.services.http.wom_queue import WomPriority


class WomHandlerBase(BaseRequestHandler):
    """Concrete base that stubs the rate-limit methods WOM mixins call.

    WiseOldManHandler overrides these stubs with real implementations.
    Inheriting from BaseRequestHandler gives mixins access to self.get,
    self.post, self.put, self.delete without attr-defined errors.
    """

    _priority: WomPriority

    async def _get_with_rate_limit(
        self, path: str, *, params: dict | None = None
    ) -> httpx.Response:
        raise NotImplementedError

    async def _write_with_rate_limit(
        self, method: str, path: str, *, json: dict | None = None
    ) -> httpx.Response:
        raise NotImplementedError
