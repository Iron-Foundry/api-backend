from __future__ import annotations

from httpx import AsyncClient

_UUID = "00000000-0000-0000-0000-000000000001"


async def test_overview_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/staff/overview")
    assert resp.status_code == 401


async def test_overview_with_auth(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/staff/overview")
    assert resp.status_code == 200


async def test_overview_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/staff/overview")
    assert resp.status_code == 403


async def test_referral_stats_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/staff/referral-stats")
    assert resp.status_code == 401


async def test_referral_stats_with_auth(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/staff/referral-stats")
    assert resp.status_code == 200


async def test_staff_members_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/staff/members")
    assert resp.status_code == 401


async def test_staff_members_list(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/staff/members")
    assert resp.status_code == 200


async def test_staff_members_list_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/staff/members")
    assert resp.status_code == 403


async def test_staff_member_detail(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/staff/members/999999999999999999")
    assert resp.status_code in (200, 404)


async def test_update_member_rsn_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/staff/members/123/rsn", json={"rsn": "NewRsn"})
    assert resp.status_code == 401


async def test_update_member_rsn_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch("/staff/members/123/rsn", json={"rsn": "NewRsn"})
    assert resp.status_code == 403


async def test_update_member_rsn_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch("/staff/members/123/rsn", json={"rsn": "NewRsn"})
    assert resp.status_code in (200, 404, 422)


async def test_staff_tickets_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/staff/tickets")
    assert resp.status_code == 401


async def test_staff_tickets_list(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/staff/tickets")
    assert resp.status_code == 200


async def test_staff_tickets_list_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/staff/tickets")
    assert resp.status_code == 403


async def test_staff_ticket_transcript_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get(f"/staff/tickets/{_UUID}/transcript")
    assert resp.status_code == 401
