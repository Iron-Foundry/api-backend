"""Foundry's OSRSClans image route: one fetch per image, then its own copy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client

_WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def _serving(
    seen: list[httpx.Request], status: int = 200, kind: str = "image/webp"
) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=_WEBP, headers={"content-type": kind})

    return httpx.MockTransport(answer)


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def test_image_is_fetched_once_then_served_from_disk(
    anon_client: AsyncClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _serving(seen))
    path = "/reference/osrs/images/sprites/197.webp?frame=2"

    first = await anon_client.get(path)
    second = await anon_client.get(path)

    assert first.content == second.content == _WEBP
    assert len(seen) == 1
    assert seen[0].url.path == "/api/v1/osrs/sprites/197.webp"
    assert seen[0].url.params["frame"] == "2"
    assert (upload_dir / "osrsclans" / "sprites" / "197-f2.webp").read_bytes() == _WEBP
    assert second.headers["cache-control"].startswith("public, max-age=")


async def test_missing_image_is_404_and_remembered(
    anon_client: AsyncClient,
    mock_valkey: AsyncMock,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "_transport", _serving([], status=404))

    resp = await anon_client.get("/reference/osrs/images/npcs/7551.webp")

    assert resp.status_code == 404
    keys = [c.args[0] for c in mock_valkey.set.await_args_list]
    assert any(k.startswith("osrsclans:image-missing:") for k in keys)


async def test_non_image_answer_is_502_and_unstored(
    anon_client: AsyncClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "_transport", _serving([], kind="text/html"))

    resp = await anon_client.get("/reference/osrs/images/items/4151.webp")

    assert resp.status_code == 502
    assert not (upload_dir / "osrsclans").exists()


async def test_svg_carries_a_script_blocking_policy(
    anon_client: AsyncClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "_transport", _serving([], kind="image/svg+xml"))

    resp = await anon_client.get("/reference/osrs/images/sprites/197.svg?frame=0")

    assert resp.headers["content-type"] == "image/svg+xml"
    assert "default-src 'none'" in resp.headers["content-security-policy"]


@pytest.mark.parametrize(
    "path",
    [
        "/reference/osrs/images/models/1.webp",
        "/reference/osrs/images/items/1.png",
        "/reference/osrs/images/items/1.webp?scale=huge",
        "/reference/osrs/images/items/1.webp?frame=-1",
    ],
)
async def test_image_route_refuses_unknown_asks(
    anon_client: AsyncClient, path: str
) -> None:
    assert (await anon_client.get(path)).status_code in (404, 422)
