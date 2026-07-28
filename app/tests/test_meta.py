from __future__ import annotations

import re

from httpx import AsyncClient

from app.version import VERSION

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


async def test_health_reports_ok(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_version_reports_package_version(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "api-backend"
    assert body["version"] == VERSION


async def test_declared_version_is_semver() -> None:
    assert _SEMVER.match(VERSION), f"version {VERSION!r} is not MAJOR.MINOR.PATCH"


async def test_version_provenance_null_outside_container(
    anon_client: AsyncClient,
) -> None:
    """GIT_SHA/BUILD_TIME are injected as image build args, not set in tests."""
    body = (await anon_client.get("/version")).json()
    assert body["git_sha"] is None
    assert body["build_time"] is None
