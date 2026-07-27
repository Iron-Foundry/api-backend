from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from httpx import AsyncClient


async def test_ccingest_missing_key_header(auth_client: AsyncClient) -> None:
    """Missing required verification-code header → 401 or 422."""
    from app.dependencies import verify_metrics_key
    from app.tests.conftest import _app

    original = _app.dependency_overrides.pop(verify_metrics_key, None)
    try:
        resp = await auth_client.post(
            "/ccingest",
            json={"type": "broadcast", "message": "test"},
        )
        assert resp.status_code in (401, 422)
    finally:
        if original is not None:
            _app.dependency_overrides[verify_metrics_key] = original


async def test_ccingest_with_key(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/ccingest",
        json={"type": "broadcast", "message": "test message", "player": "TestPlayer"},
    )
    assert resp.status_code in (200, 204, 422)


async def test_ccingest_missing_body(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ccingest")
    assert resp.status_code == 422


async def test_ccingest_skips_foreign_clan(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    """Payloads from another clan are dropped; matching ones still process."""
    from app.services.ccingest_metrics import collector

    mock_session.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
        guild_id=1, discord_user_id=2
    )
    collector.drain()
    resp = await auth_client.post(
        "/ccingest",
        headers={"verification-code": "test-key"},
        json=[
            {
                "clan_name": "Some Other Clan",
                "sender": "Intruder",
                "message": "forged loot",
                "rank": "Member",
            },
            {
                "clan_name": "Iron\xa0Foundry",
                "sender": "GimBob",
                "message": "hello clan",
                "rank": "Member",
            },
        ],
    )
    assert resp.status_code == 200, resp.text
    metrics = collector.drain()
    assert metrics.get("wrong_clan") == 1
    assert "chat" in metrics
