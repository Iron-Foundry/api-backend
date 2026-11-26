"""The author of an open feedback post edits it, and nobody else can."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Feedback
from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

_OTHER_USER = 424242


async def _seed_post(engine: AsyncEngine, author: int, status: str) -> int:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        item = Feedback(
            type="suggestion",
            discord_user_id=author,
            is_anonymous=False,
            title="Seeded",
            description="Seeded body",
            extra={},
            status=status,
            attachment_ids=[],
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        await session.flush()
        item_id = item.id
        await session.commit()
    return item_id


async def test_author_edits_own_open_post(client: AsyncClient) -> None:
    created = await client.post(
        "/feedback/",
        json={
            "type": "bug",
            "title": "Old",
            "description": "Old body",
            "steps_to_reproduce": "Old steps",
            "is_anonymous": False,
            "attachment_ids": [],
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    edited = await client.patch(
        f"/feedback/{item_id}",
        json={"title": "New", "description": "New body", "steps_to_reproduce": "New"},
    )
    assert edited.status_code == 200, edited.text
    body = (await client.get(f"/feedback/{item_id}")).json()
    assert (body["title"], body["description"]) == ("New", "New body")
    assert body["extra"]["steps_to_reproduce"] == "New"


@pytest.mark.parametrize(
    ("author", "status", "code"),
    [(_OTHER_USER, "open", 403), (None, "planned", 400)],
)
async def test_edit_refused_for_other_or_closed(
    client: AsyncClient,
    seed_engine: AsyncEngine,
    author: int | None,
    status: str,
    code: int,
) -> None:
    owner = author if author is not None else int(TEST_USER["sub"])
    item_id = await _seed_post(seed_engine, owner, status)
    resp = await client.patch(f"/feedback/{item_id}", json={"title": "Changed"})
    assert resp.status_code == code, resp.text
