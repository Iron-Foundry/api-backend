from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.services.competition_schedule.awards import compute_award_plan
from app.services.competition_schedule.ballot_tokens import DEFAULT_TOKEN_CONFIG


def _p(name: str, gained: int) -> dict[str, Any]:
    return {"player": {"displayName": name}, "progress": {"gained": gained}}


# ── Balance endpoint ──────────────────────────────────────────────────────


async def test_balance_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/clan/ballot-tokens/me")
    assert resp.status_code == 401


async def test_balance_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/ballot-tokens/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == 0
    assert body["transactions"] == []


# ── Config endpoints ──────────────────────────────────────────────────────


async def test_config_read_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/config/ballot-tokens")
    assert resp.status_code == 401


async def test_config_read_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/config/ballot-tokens")
    assert resp.status_code == 403


async def test_config_read_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/ballot-tokens")
    assert resp.status_code == 200
    assert resp.json()["vote_cost"] == DEFAULT_TOKEN_CONFIG["vote_cost"]


async def test_config_write_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.put("/config/ballot-tokens", json={})
    assert resp.status_code == 403


async def test_config_write_staff(staff_client: AsyncClient) -> None:
    body = {
        "placement_tokens": [5, 4, 3, 2, 1],
        "bonus_threshold_pct": 10,
        "bonus_tokens": 1,
        "vote_cost": 1,
        "max_hold": 50,
    }
    resp = await staff_client.put("/config/ballot-tokens", json=body)
    assert resp.status_code == 200
    assert resp.json()["max_hold"] == 50


async def test_config_write_rejects_bad_threshold(staff_client: AsyncClient) -> None:
    body = {
        "placement_tokens": [1],
        "bonus_threshold_pct": 500,
        "bonus_tokens": 1,
        "vote_cost": 1,
        "max_hold": 10,
    }
    resp = await staff_client.put("/config/ballot-tokens", json=body)
    assert resp.status_code == 422


# ── Award math (pure) ─────────────────────────────────────────────────────


async def test_award_plan_placements_and_bonus_stack() -> None:
    ranked = [
        _p("A", 1000),
        _p("B", 900),
        _p("C", 800),
        _p("D", 700),
        _p("E", 600),
        _p("F", 500),
        _p("G", 50),
    ]
    resolved = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7}
    plan = compute_award_plan(ranked, resolved, DEFAULT_TOKEN_CONFIG)
    by_user: dict[int, list[tuple[int, str]]] = {}
    for uid, amount, reason in plan:
        by_user.setdefault(uid, []).append((amount, reason))
    assert (10, "placement_award") in by_user[1]
    assert (1, "bonus_award") in by_user[1]
    assert by_user[6] == [(1, "bonus_award")]
    assert 7 not in by_user


async def test_award_plan_skips_unresolved() -> None:
    ranked = [_p("A", 1000), _p("Ghost", 800)]
    plan = compute_award_plan(ranked, {"a": 1}, DEFAULT_TOKEN_CONFIG)
    assert all(uid == 1 for uid, _, _ in plan)


async def test_award_plan_empty_when_no_gains() -> None:
    ranked = [_p("A", 0), _p("B", 0)]
    plan = compute_award_plan(ranked, {"a": 1, "b": 2}, DEFAULT_TOKEN_CONFIG)
    assert plan == []
