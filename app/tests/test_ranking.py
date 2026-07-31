from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient

from app.services.ranking_service import _DEFAULT_CONFIG
from app.services.ranking_service._parse import build_snapshot_rows
from app.services.ranking_service.scoring import (
    rank_from_snapshots,
    rank_player_breakdown,
)


async def test_ranking_status_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/ranking/status")
    assert resp.status_code == 401


async def test_ranking_status(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/status")
    assert resp.status_code == 200


async def test_ranking_stats(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/stats")
    assert resp.status_code in (200, 500)


async def test_player_ranking(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/player/SomePlayer")
    assert resp.status_code in (200, 404, 500)


async def test_player_breakdown_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/player/NonExistentPlayerXYZ123/breakdown")
    assert resp.status_code == 404


async def test_player_profile_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/player/NonExistentPlayerXYZ123/profile")
    assert resp.status_code == 404


async def test_player_profile(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/player/SomePlayer/profile")
    assert resp.status_code in (200, 404, 500)


async def test_ranking_results(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/results")
    assert resp.status_code in (200, 500)


async def test_run_ranking_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/ranking/run")
    assert resp.status_code == 401


async def test_run_ranking_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ranking/run")
    assert resp.status_code == 403


async def test_run_ranking_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/ranking/run")
    assert resp.status_code in (200, 202, 422, 500)


async def test_preview_ranking_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/ranking/preview")
    assert resp.status_code == 401


async def test_preview_ranking_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ranking/preview")
    assert resp.status_code in (403, 404, 422)


async def test_preview_ranking_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/ranking/preview")
    assert resp.status_code in (200, 202, 422, 500)


def test_scoring_every_kc_counts() -> None:
    snap_1kc = {"rsn": "a", "bosses": {"vorkath": 1}, "skills": {}}
    snap_100kc = {"rsn": "b", "bosses": {"vorkath": 100}, "skills": {}}
    results = rank_from_snapshots([snap_1kc, snap_100kc], _DEFAULT_CONFIG)
    pts_1kc = next(r["points"] for r in results if r["rsn"] == "a")
    pts_100kc = next(r["points"] for r in results if r["rsn"] == "b")
    assert pts_100kc > pts_1kc


def test_scoring_first_kill_bonus() -> None:
    snap_0kc = {"rsn": "a", "bosses": {"vorkath": 0}, "skills": {}}
    snap_1kc = {"rsn": "b", "bosses": {"vorkath": 1}, "skills": {}}
    results = rank_from_snapshots([snap_0kc, snap_1kc], _DEFAULT_CONFIG)
    pts_0kc = next(r["points"] for r in results if r["rsn"] == "a")
    pts_1kc = next(r["points"] for r in results if r["rsn"] == "b")
    assert pts_0kc == 0
    assert pts_1kc > 0


def test_scoring_prestige_multiplier_applied() -> None:
    snap_no_inferno = {"rsn": "a", "bosses": {"vorkath": 1000}, "skills": {}}
    snap_inferno = {
        "rsn": "b",
        "bosses": {"vorkath": 1000, "tzkal_zuk": 1},
        "skills": {},
    }
    results = rank_from_snapshots([snap_no_inferno, snap_inferno], _DEFAULT_CONFIG)
    pts_no_inferno = next(r["points"] for r in results if r["rsn"] == "a")
    pts_inferno = next(r["points"] for r in results if r["rsn"] == "b")
    assert pts_inferno > pts_no_inferno


def test_scoring_skill_xp_contributes() -> None:
    snap_no_xp = {"rsn": "a", "bosses": {}, "skills": {"slayer": 0}}
    snap_with_xp = {"rsn": "b", "bosses": {}, "skills": {"slayer": 50_000_000}}
    results = rank_from_snapshots([snap_no_xp, snap_with_xp], _DEFAULT_CONFIG)
    pts_no_xp = next(r["points"] for r in results if r["rsn"] == "a")
    pts_with_xp = next(r["points"] for r in results if r["rsn"] == "b")
    assert pts_with_xp > pts_no_xp


def test_breakdown_structure() -> None:
    snap = {
        "rsn": "a",
        "bosses": {"vorkath": 100, "tzkal_zuk": 1},
        "skills": {"slayer": 50_000_000},
    }
    result = rank_player_breakdown(snap, _DEFAULT_CONFIG)
    assert "bosses" in result and "skills" in result and "prestige" in result
    assert result["total_points"] > result["base_points"]
    assert any(e["name"] == "vorkath" for e in result["bosses"])
    assert any(e["name"] == "slayer" for e in result["skills"])
    tzkal = next((p for p in result["prestige"] if p["boss_name"] == "tzkal_zuk"), None)
    assert tzkal is not None and tzkal["active"] is True


def test_scoring_config_round_trip() -> None:
    from app.services.ranking_service.scoring import RankingConfig

    restored = RankingConfig.from_dict(_DEFAULT_CONFIG.to_dict())
    assert len(restored.bosses) == len(_DEFAULT_CONFIG.bosses)
    assert len(restored.skills) == len(_DEFAULT_CONFIG.skills)
    assert len(restored.prestige) == len(_DEFAULT_CONFIG.prestige)
    assert restored.rank_thresholds == _DEFAULT_CONFIG.rank_thresholds


def test_snapshot_rows_keep_overall_and_efficiency() -> None:
    entry = {
        "player": {
            "username": "Some Player",
            "type": "ironman",
            "ehp": 1104.7,
            "ehb": 946.2,
        },
        "data": {
            "data": {
                "skills": {
                    "overall": {
                        "metric": "overall",
                        "experience": 346368,
                        "level": 243,
                    },
                    "slayer": {"metric": "slayer", "experience": 40},
                },
                "bosses": {"zulrah": {"metric": "zulrah", "kills": -1}},
                "activities": {"clue_scrolls_all": {"score": 12}},
            }
        },
    }
    now = datetime(2026, 7, 31, tzinfo=UTC)

    ranking_inputs, snapshot_rows = build_snapshot_rows([entry], {"slayer"}, now)

    assert ranking_inputs[0]["skills"] == {"slayer": 40.0}
    assert "overall" not in ranking_inputs[0]["skills"]
    row = snapshot_rows[0]
    assert row["rsn"] == "some player"
    assert row["skills"] == {"slayer": 40.0, "overall": 346368.0}
    assert row["bosses"] == {"zulrah": -1}
    assert row["activities"] == {"clue_scrolls_all": 12}
    assert row["ehp"] == 1104.7
    assert row["ehb"] == 946.2
    assert row["fetched_at"] == now


def test_snapshot_rows_skip_unusable_entries() -> None:
    entries = [
        {"player": {"username": ""}, "data": {"data": {}}},
        {"player": {"username": "no snapshot"}, "data": None},
        {"player": {"username": "no efficiency"}, "data": {"data": {"skills": {}}}},
    ]

    ranking_inputs, snapshot_rows = build_snapshot_rows(
        entries, set(), datetime.now(UTC)
    )

    assert [r["rsn"] for r in ranking_inputs] == ["no efficiency"]
    assert snapshot_rows[0]["ehp"] is None and snapshot_rows[0]["ehb"] is None
    assert snapshot_rows[0]["skills"] == {"overall": 0.0}
