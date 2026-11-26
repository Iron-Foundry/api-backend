"""A member's frenzy signup round trip against the real database."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import FrenzyEvent, FrenzyTemplate, User, UserAccount
from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

_MEMBER = int(TEST_USER["sub"])


async def _seed(engine: AsyncEngine, signups_open: bool = True) -> tuple[int, int]:
    """An active event and a member with a primary and an alt; returns the event and alt ids."""
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        template = FrenzyTemplate(name="Seeded", created_at=now, updated_at=now)
        session.add(template)
        await session.flush()
        event = FrenzyEvent(
            name="Winter Frenzy",
            template_id=template.id,
            is_active=True,
            signups_open=signups_open,
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        session.add(
            User(
                discord_user_id=_MEMBER,
                discord_username="Signup Tester",
                created_at=now,
                updated_at=now,
            )
        )
        main = UserAccount(
            discord_user_id=_MEMBER, rsn="Main Iron", is_primary=True, created_at=now
        )
        alt = UserAccount(
            discord_user_id=_MEMBER, rsn="Alt Iron", is_primary=False, created_at=now
        )
        session.add_all([main, alt])
        await session.flush()
        ids = (event.id, alt.id)
        await session.commit()
    return ids


async def test_member_signs_up_switches_and_withdraws(
    client: AsyncClient, staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id, alt_id = await _seed(seed_engine)
    path = f"/frenzy/events/{event_id}/signup"

    created = await client.post(path, json={"timezone": "America/New_York"})
    assert created.status_code == 201
    assert created.json()["rsn"] == "Main Iron"
    assert created.json()["timezone"] == "America/New_York"
    active = (await client.get("/frenzy/active")).json()
    assert active["signups_open"] is True
    assert active["my_signup"]["rsn"] == "Main Iron"

    assert (await client.patch(path, json={"account_id": alt_id})).status_code == 204
    listed = (await staff_client.get(f"/frenzy/events/{event_id}/signups")).json()
    assert listed["total"] == 1
    assert listed["items"][0] | {"signed_up_at": None, "id": None} == {
        "id": None,
        "wants_captain": False,
        "discord_user_id": str(_MEMBER),
        "discord_username": "Signup Tester",
        "account_id": alt_id,
        "rsn": "Alt Iron",
        "signed_up_at": None,
    }

    assert (await client.delete(path)).status_code == 204
    assert (await client.get("/frenzy/active")).json()["my_signup"] is None


@pytest.mark.parametrize(
    ("signups_open", "first_body", "second_body", "code"),
    [
        (False, None, {}, 403),
        (True, {}, {}, 409),
        (True, None, {"account_id": 999_999}, 422),
        (True, None, {"timezone": "Mars/Olympus_Mons"}, 422),
    ],
)
async def test_signup_refusals(
    client: AsyncClient,
    seed_engine: AsyncEngine,
    signups_open: bool,
    first_body: dict[str, int] | None,
    second_body: dict[str, int],
    code: int,
) -> None:
    event_id, _ = await _seed(seed_engine, signups_open=signups_open)
    path = f"/frenzy/events/{event_id}/signup"
    if first_body is not None:
        assert (await client.post(path, json=first_body)).status_code == 201
    resp = await client.post(path, json=second_body)
    assert resp.status_code == code, resp.text
