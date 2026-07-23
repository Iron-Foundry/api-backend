"""Real-DB lifecycle for the surveys router: staff create -> open -> persistence."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_survey_create_and_open(staff_client: AsyncClient, seed_engine) -> None:
    payload = {
        "title": "Applicant Screening",
        "category": "application",
        "fields": [{"id": "q1", "type": "text", "label": "Your RSN", "required": True}],
    }
    created = await staff_client.post("/surveys/", json=payload)
    assert created.status_code == 201, created.text
    template_id = created.json()["template_id"]
    assert created.json()["is_open"] is False

    async with seed_engine.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT title, questions FROM survey_templates "
                    "WHERE template_id = :tid"
                ),
                {"tid": template_id},
            )
        ).one()
    assert row.title == "Applicant Screening"
    assert row.questions["fields"][0]["label"] == "Your RSN"

    opened = await staff_client.patch(
        f"/surveys/{template_id}/open", json={"is_open": True}
    )
    assert opened.status_code == 200
    assert opened.json()["is_open"] is True

    async with seed_engine.connect() as conn:
        questions = (
            await conn.execute(
                sa.text(
                    "SELECT questions FROM survey_templates WHERE template_id = :tid"
                ),
                {"tid": template_id},
            )
        ).scalar_one()
    assert questions["is_open"] is True


async def test_create_survey_non_staff_forbidden(client: AsyncClient) -> None:
    resp = await client.post("/surveys/", json={"title": "x", "fields": []})
    assert resp.status_code == 403
