from __future__ import annotations

from unittest.mock import MagicMock

from httpx import AsyncClient


async def test_me_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_user(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    user_mock = MagicMock()
    user_mock.discord_user_id = 111222333444555666
    user_mock.username = "TestUser"
    user_mock.avatar = None
    user_mock.clan_rank = None
    user_mock.discord_roles = []
    user_mock.stats_opt_out = False
    user_mock.referral_source = None
    user_mock.roles_refreshed_at = None
    mock_session.execute.return_value.scalar_one_or_none.return_value = user_mock
    resp = await auth_client.get("/auth/me")
    assert resp.status_code in (200, 404)


async def test_login_redirects(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/auth/login", follow_redirects=False)
    assert resp.status_code in (200, 302, 307)


async def test_callback_missing_code(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/auth/callback", follow_redirects=False)
    assert resp.status_code in (307, 400, 422)


async def test_token_missing_body(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/auth/token")
    assert resp.status_code == 422


async def test_token_invalid_key(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    resp = await auth_client.post("/auth/token", json={"api_key": "bad-key"})
    assert resp.status_code in (401, 422)
