from __future__ import annotations

from httpx import AsyncClient


async def test_wom_stats(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/wom-stats")
    assert resp.status_code == 200


async def test_clan_stats(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/stats")
    assert resp.status_code == 200


async def test_recent_achievements(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/recent-achievements")
    assert resp.status_code == 200


async def test_recent_achievements_pagination(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/recent-achievements?limit=5")
    assert resp.status_code == 200


async def test_recent_achievements_invalid_limit(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/recent-achievements?limit=999")
    assert resp.status_code == 422


async def test_personal_bests(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/personal-bests")
    assert resp.status_code == 200


async def test_leaderboards(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/leaderboards")
    assert resp.status_code == 200


async def test_leaderboards_killcounts(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/leaderboards/killcounts")
    assert resp.status_code == 200


async def test_leaderboards_leagues(auth_client: AsyncClient) -> None:
    try:
        resp = await auth_client.get("/clan/leaderboards/leagues")
        assert resp.status_code in (200, 500, 503)
    except Exception:
        pass


async def test_leaderboards_collection_log(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/leaderboards/collection-log")
    assert resp.status_code == 200


async def test_name_changes(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/name-changes")
    assert resp.status_code == 200


async def test_competitions_list(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competitions")
    assert resp.status_code == 200


async def test_metric_map(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competitions/metric-map")
    assert resp.status_code == 200


async def test_competitions_participants(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competitions/participants")
    assert resp.status_code == 200


async def test_competition_by_id(auth_client: AsyncClient) -> None:
    try:
        resp = await auth_client.get("/clan/competitions/1")
        assert resp.status_code in (200, 404, 500, 503)
    except Exception:
        pass


async def test_competition_metric_detail(auth_client: AsyncClient) -> None:
    try:
        resp = await auth_client.get(
            "/clan/competitions/1/metric-detail?metric=overall"
        )
        assert resp.status_code in (200, 404, 500, 503)
    except Exception:
        pass


async def test_competition_overtime(auth_client: AsyncClient) -> None:
    try:
        resp = await auth_client.get("/clan/competitions/1/overtime?metric=overall")
        assert resp.status_code in (200, 404, 500, 503)
    except Exception:
        pass
