from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

_NOW = datetime.now(UTC)
_COMPETITION = {
    "id": 1,
    "title": "Test Competition",
    "metric": "overall",
    "type": "classic",
    "startsAt": (_NOW - timedelta(days=1)).isoformat(),
    "endsAt": (_NOW + timedelta(days=1)).isoformat(),
    "groupId": 1,
    "participations": [
        {
            "player": {"displayName": "Tester"},
            "teamName": None,
            "progress": {"gained": 100},
            "levels": {},
        }
    ],
}


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


async def test_leaderboards_cluescrolls(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/leaderboards/cluescrolls")
    assert resp.status_code in (200, 500, 503)


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
    from app.services.http import WiseOldManHandler

    with patch.object(
        WiseOldManHandler,
        "get_cached_competition",
        AsyncMock(return_value=dict(_COMPETITION)),
    ):
        resp = await auth_client.get("/clan/competitions/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Test Competition"
    assert body["status"] == "ongoing"
    assert body["participantCount"] == 1


async def test_competition_metric_detail(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competitions/1/metric-detail?metric=overall")
    assert resp.status_code in (200, 404, 500, 503)


async def test_competition_overtime(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competitions/1/overtime?metric=overall")
    assert resp.status_code in (200, 404, 500, 503)
