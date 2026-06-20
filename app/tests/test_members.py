from __future__ import annotations

from httpx import AsyncClient


async def test_my_stats_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/stats")
    assert resp.status_code == 401


async def test_my_stats(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/members/me/stats")
    assert resp.status_code in (200, 404)


async def test_update_privacy_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/members/me/privacy", json={})
    assert resp.status_code == 401


async def test_update_privacy(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch("/members/me/privacy", json={"stats_opt_out": False})
    assert resp.status_code in (200, 404, 422)


async def test_update_referral_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/members/me/referral", json={})
    assert resp.status_code == 401


async def test_update_referral(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch(
        "/members/me/referral", json={"referral_source": "friend"}
    )
    assert resp.status_code in (200, 404, 422)


async def test_avatar_redirect(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(
        "/members/111222333444555666/avatar", follow_redirects=False
    )
    assert resp.status_code in (200, 301, 302, 307, 404)


async def test_api_key_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/api-key")
    assert resp.status_code == 401


async def test_api_key(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/members/me/api-key")
    assert resp.status_code in (200, 404)


async def test_rotate_api_key_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/members/me/api-key/rotate")
    assert resp.status_code == 401


async def test_accounts_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/accounts")
    assert resp.status_code == 401


async def test_accounts(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/members/me/accounts")
    assert resp.status_code == 200


async def test_link_account_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/members/me/accounts", json={"rsn": "TestRsn"})
    assert resp.status_code == 401


async def test_link_account(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/members/me/accounts", json={"rsn": "TestRsn"})
    assert resp.status_code in (200, 201, 404, 422)


async def test_unlink_account_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/members/me/accounts/1")
    assert resp.status_code == 401


async def test_rankings_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/rankings")
    assert resp.status_code == 401


async def test_feed_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/feed")
    assert resp.status_code == 401


async def test_feed(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/members/me/feed")
    assert resp.status_code == 200


async def test_tickets_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/members/me/tickets")
    assert resp.status_code == 401


async def test_tickets(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/members/me/tickets")
    assert resp.status_code == 200
