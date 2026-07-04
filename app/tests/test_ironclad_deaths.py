from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.routers.ironclad._helpers import sanitize_content

_VALID_PAYLOAD: dict[str, Any] = {
    "content": "Zezima has died.",
    "extra": {
        "valueLost": 0,
        "isPvp": False,
        "keptItems": [],
        "lostItems": [],
    },
    "type": "DEATH",
    "playerName": "Zezima",
    "accountType": "IRONMAN",
    "seasonalWorld": False,
    "dinkAccountHash": "abc123",
    "embeds": [],
}

_MEMBERS = frozenset(["zezima"])
_PATH = "/ironclad/sanitize/deaths"


def _mock_cache(members: frozenset[str] = _MEMBERS) -> MagicMock:
    cache = MagicMock()
    cache.get_members = AsyncMock(return_value=members)
    return cache


async def test_json_valid_member(anon_client: AsyncClient) -> None:
    with (
        patch("app.routers.ironclad.deaths.ironclad_wom_cache", _mock_cache()),
        patch("app.routers.ironclad.deaths.forward_to_webhook", new_callable=AsyncMock),
    ):
        resp = await anon_client.post(_PATH, json=_VALID_PAYLOAD)
    assert resp.status_code == 204


async def test_json_player_not_in_group(anon_client: AsyncClient) -> None:
    with patch(
        "app.routers.ironclad.deaths.ironclad_wom_cache",
        _mock_cache(frozenset()),
    ):
        resp = await anon_client.post(_PATH, json=_VALID_PAYLOAD)
    assert resp.status_code == 422


async def test_json_wrong_type(anon_client: AsyncClient) -> None:
    payload = {**_VALID_PAYLOAD, "type": "LOGIN"}
    resp = await anon_client.post(_PATH, json=payload)
    assert resp.status_code == 422


async def test_json_missing_fields(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(_PATH, json={})
    assert resp.status_code == 422


async def test_multipart_with_image(anon_client: AsyncClient) -> None:
    with (
        patch("app.routers.ironclad.deaths.ironclad_wom_cache", _mock_cache()),
        patch("app.routers.ironclad.deaths.forward_to_webhook", new_callable=AsyncMock),
    ):
        resp = await anon_client.post(
            _PATH,
            data={"payload_json": json.dumps(_VALID_PAYLOAD)},
            files={"file": ("death.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
    assert resp.status_code == 204


async def test_multipart_image_too_large(anon_client: AsyncClient) -> None:
    with (
        patch("app.routers.ironclad.deaths.ironclad_wom_cache", _mock_cache()),
        patch("app.routers.ironclad.deaths.forward_to_webhook", new_callable=AsyncMock),
    ):
        resp = await anon_client.post(
            _PATH,
            data={"payload_json": json.dumps(_VALID_PAYLOAD)},
            files={"file": ("big.png", b"x" * (8 * 1024 * 1024 + 1), "image/png")},
        )
    assert resp.status_code == 422


async def test_multipart_wrong_image_type(anon_client: AsyncClient) -> None:
    with (
        patch("app.routers.ironclad.deaths.ironclad_wom_cache", _mock_cache()),
        patch("app.routers.ironclad.deaths.forward_to_webhook", new_callable=AsyncMock),
    ):
        resp = await anon_client.post(
            _PATH,
            data={"payload_json": json.dumps(_VALID_PAYLOAD)},
            files={"file": ("anim.gif", b"GIF89a", "image/gif")},
        )
    assert resp.status_code == 422


async def test_multipart_missing_payload_json(anon_client: AsyncClient) -> None:
    resp = await anon_client.post(
        _PATH,
        files={"file": ("death.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert resp.status_code == 422


def test_sanitize_content_unit() -> None:
    assert "@everyone" not in sanitize_content("hey @everyone look")
    assert "@here" not in sanitize_content("@here notice")
    assert "<@123456>" not in sanitize_content("ping <@123456>")
    assert "<@!789>" not in sanitize_content("ping <@!789>")
    assert "<@&999>" not in sanitize_content("<@&999> clan")
    assert "https://" not in sanitize_content("see https://evil.com for loot")
    assert sanitize_content("clean text") == "clean text"
