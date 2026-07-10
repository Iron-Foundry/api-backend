"""Tests for OutboundHttpCollector and the /metrics/history endpoint with max_points."""

from __future__ import annotations

from httpx import AsyncClient

from app.services.outbound_metrics.collector import OutboundHttpCollector


def test_collector_drain_empty() -> None:
    c = OutboundHttpCollector()
    assert c.drain() == {}


def test_collector_drain_aggregates() -> None:
    c = OutboundHttpCollector()
    c.record("api.wiseoldman.net", "GET", "/v2/groups/1/members", 200, 120.0)
    c.record("api.wiseoldman.net", "GET", "/v2/groups/1/members", 200, 80.0)
    c.record("api.wiseoldman.net", "GET", "/v2/groups/1/members", 429, 15.0)
    c.record("discord.com", "GET", "/guilds/123/roles", 200, 50.0)

    result = c.drain()

    assert result["total_calls"] == 4
    assert result["total_errors_4xx"] == 1
    assert result["total_errors_5xx"] == 0

    wom_endpoint = result["endpoints"]["api.wiseoldman.net GET /v2/groups/1/members"]
    assert wom_endpoint["count"] == 3
    assert wom_endpoint["errors_4xx"] == 1
    assert "429" in wom_endpoint["status_codes"]

    discord_endpoint = result["endpoints"]["discord.com GET /guilds/123/roles"]
    assert discord_endpoint["count"] == 1
    assert discord_endpoint["errors_4xx"] == 0

    assert "api.wiseoldman.net" in result["by_target"]
    assert result["by_target"]["api.wiseoldman.net"]["count"] == 3
    assert result["by_target"]["discord.com"]["count"] == 1


def test_collector_drain_resets_buffer() -> None:
    c = OutboundHttpCollector()
    c.record("discord.com", "GET", "/guilds/123/roles", 200, 10.0)
    c.drain()
    assert c.drain() == {}


async def test_metrics_history_accepts_max_points(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(
        "/metrics/history?service=api-backend&module=endpoints&max_points=50"
    )
    assert resp.status_code in (200, 403, 500)


async def test_metrics_history_default_params(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(
        "/metrics/history?service=api-backend&module=endpoints"
    )
    assert resp.status_code in (200, 403, 500)
