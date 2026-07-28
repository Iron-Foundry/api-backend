from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from httpx import AsyncClient


def _authenticate(mock_session: MagicMock) -> None:
    """Make verify_clan resolve the verification-code header to a clan member."""
    mock_session.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
        guild_id=1, discord_user_id=2
    )


async def test_ccingest_missing_key_header(auth_client: AsyncClient) -> None:
    """No verification-code header at all → 401, before any body validation."""
    resp = await auth_client.post("/ccingest", json=[])
    assert resp.status_code == 401


async def test_ccingest_unknown_key(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    """A key that matches no active user → 401."""
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    resp = await auth_client.post(
        "/ccingest", headers={"verification-code": "revoked-key"}, json=[]
    )
    assert resp.status_code == 401


async def test_ccingest_with_key(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    _authenticate(mock_session)
    resp = await auth_client.post(
        "/ccingest",
        headers={"verification-code": "test-key"},
        json=[
            {
                "clan_name": "Iron\xa0Foundry",
                "sender": "GimBob",
                "message": "test message",
                "rank": "Member",
            }
        ],
    )
    assert resp.status_code == 200, resp.text


async def test_ccingest_missing_body(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    _authenticate(mock_session)
    resp = await auth_client.post(
        "/ccingest", headers={"verification-code": "test-key"}
    )
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
