"""Smoke tests: verify every router root is reachable and returns no redirect."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_GET_ROOTS: list[tuple[str, int]] = [
    ("/health", 200),
    ("/feedback/", 200),
    ("/badges/", 200),
    ("/parties/", 200),
    ("/surveys/", 200),
]


@pytest.mark.parametrize("path,expected", _GET_ROOTS)
async def test_root_get_reachable(
    auth_client: AsyncClient, path: str, expected: int
) -> None:
    resp = await auth_client.get(path)
    assert resp.status_code == expected, (
        f"GET {path} returned {resp.status_code} (expected {expected})"
    )


@pytest.mark.parametrize("path,expected", _GET_ROOTS)
async def test_root_get_no_redirect(
    no_redirect_auth_client: AsyncClient, path: str, expected: int
) -> None:
    """Ensure root endpoints respond directly without a redirect.

    A 3xx here means the route is registered with a trailing slash mismatch,
    which causes broken redirects behind a TLS-terminating proxy.
    """
    resp = await no_redirect_auth_client.get(path)
    assert resp.status_code < 300, (
        f"GET {path} returned redirect {resp.status_code} "
        f"-> {resp.headers.get('location', '?')} "
        f"(route registered with wrong path suffix)"
    )
    assert resp.status_code < 500, (
        f"GET {path} returned server error {resp.status_code}"
    )
