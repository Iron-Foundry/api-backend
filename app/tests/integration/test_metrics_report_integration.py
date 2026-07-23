"""The discord -> api metrics seam, exercised against a real database."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.dependencies import verify_metrics_key

pytestmark = pytest.mark.integration


async def test_report_persists_status_and_record(
    app, client: AsyncClient, db_url: str
) -> None:
    app.dependency_overrides[verify_metrics_key] = lambda: None

    payload = {
        "service_name": "discord-server",
        "module_name": "tickets",
        "uptime_seconds": 123,
        "is_healthy": True,
        "metrics": {"open_count": 3, "closed_today": 1},
    }
    resp = await client.post("/metrics/report", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            status = (
                await conn.execute(
                    sa.text(
                        "SELECT is_healthy, uptime_seconds, summary_metrics "
                        "FROM service_status WHERE service_name = :name"
                    ),
                    {"name": "discord-server"},
                )
            ).one()
            assert status.is_healthy is True
            assert status.uptime_seconds == 123
            assert status.summary_metrics == payload["metrics"]

            record_count = (
                await conn.execute(
                    sa.text(
                        "SELECT count(*) FROM metric_records "
                        "WHERE service_name = :s AND module_name = :m"
                    ),
                    {"s": "discord-server", "m": "tickets"},
                )
            ).scalar_one()
            assert record_count == 1
    finally:
        await engine.dispose()
