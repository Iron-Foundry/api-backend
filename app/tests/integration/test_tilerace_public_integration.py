"""Real-DB proof that GET /tilerace/active never ships what it withholds.

Fog of war used to be enforced only by the browser, so any anonymous caller
could read the whole unrevealed board, the roster, and the Discord ids off the
public endpoint. These tests pin the masking to the response itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
    TileRepositoryTile,
    User,
    UserAccount,
)
from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

_VIEWER_ID = int(TEST_USER["sub"])
_TEAMMATE_ID = 777000111
_HIDDEN_TITLE = "Behind the fog"


async def _seed_active_event(engine: AsyncEngine) -> dict[str, int]:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        await session.execute(
            sa.update(TileRaceEvent)
            .where(TileRaceEvent.is_active.is_(True))
            .values(is_active=False)
        )
        revealed = TileRepositoryTile(
            title="Revealed",
            description="visible",
            items=[],
            tags=[],
            created_at=now,
            updated_at=now,
        )
        hidden = TileRepositoryTile(
            title=_HIDDEN_TITLE,
            description="secret",
            items=[],
            tags=[],
            created_at=now,
            updated_at=now,
        )
        session.add_all([revealed, hidden])
        await session.flush()
        event = TileRaceEvent(
            name="Fog Test",
            is_active=True,
            fog_of_war=True,
            signups_open=True,
            cells=[
                {
                    "cell_x": 0,
                    "cell_y": 0,
                    "path_position": 1,
                    "tile_id": str(revealed.id),
                    "modifiers": [],
                },
                {
                    "cell_x": 1,
                    "cell_y": 0,
                    "path_position": 2,
                    "tile_id": str(hidden.id),
                    "modifiers": [{"type": "trap", "dice_count": 1, "dice_sides": 6}],
                },
            ],
            discord_category_id=1234,
            discord_captains_role_id=5678,
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        team = TileRaceTeam(
            event_id=event.id,
            name="Reds",
            slug="reds",
            icon_type="npc",
            icon_url="",
            color="#f00",
            position=1,
            furthest_position=1,
            discord_role_id=4321,
            pending_effects={"skip_next": True},
            updated_at=now,
        )
        session.add(team)
        await session.flush()
        accounts: dict[str, int] = {}
        for discord_id, rsn in ((_VIEWER_ID, "viewer"), (_TEAMMATE_ID, "teammate")):
            if await session.get(User, discord_id) is None:
                session.add(
                    User(
                        discord_user_id=discord_id,
                        discord_username=rsn,
                        created_at=now,
                        updated_at=now,
                    )
                )
            account = (
                await session.execute(
                    sa.select(UserAccount).where(UserAccount.rsn == rsn)
                )
            ).scalar_one_or_none()
            if account is None:
                account = UserAccount(
                    discord_user_id=discord_id,
                    rsn=rsn,
                    is_primary=True,
                    created_at=now,
                )
                session.add(account)
                await session.flush()
            accounts[rsn] = account.id
        session.add_all(
            [
                TileRaceSignup(
                    event_id=event.id,
                    discord_user_id=_VIEWER_ID,
                    team_id=team.id,
                    account_id=accounts["viewer"],
                    rsn="viewer",
                    ranking_score=500,
                    wants_captain=True,
                    is_captain=True,
                    signed_up_at=now,
                ),
                TileRaceSignup(
                    event_id=event.id,
                    discord_user_id=_TEAMMATE_ID,
                    team_id=team.id,
                    account_id=accounts["teammate"],
                    rsn="teammate",
                    ranking_score=400,
                    signed_up_at=now,
                ),
            ]
        )
        await session.commit()
        return accounts


async def test_anonymous_board_hides_fogged_tiles_and_private_state(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await _seed_active_event(seed_engine)

    resp = await anon_client.get("/tilerace/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert _HIDDEN_TITLE not in resp.text, "a fogged tile reached the wire"
    assert "trap" not in resp.text, "a fogged cell's modifiers reached the wire"
    assert "1234" not in resp.text, "a Discord id reached the wire"

    revealed, fogged = body["cells"]
    assert revealed["tile"]["title"] == "Revealed"
    assert fogged == {"cell_x": 1, "cell_y": 0, "path_position": 2}

    team = body["teams"][0]
    assert "pending_effects" not in team
    assert team["members"] == [
        {"rsn": "viewer", "is_captain": True},
        {"rsn": "teammate", "is_captain": False},
    ]
    assert "signups" not in body
    assert body["signup_count"] == 2
    assert body["my_signup"] is None and body["my_team_id"] is None
    assert not [k for k in body if k.startswith("discord_")]


async def test_active_falls_back_to_an_event_whose_end_date_has_passed(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    """A stopped event still has a recap to show.

    Staff stop an event by deactivating it, which used to leave the page with
    nothing: the fallback only looked for `is_finished`, and that is set solely
    by a finish pad whose `ends_game` trigger is on.
    """
    await _seed_active_event(seed_engine)
    now = datetime.now(UTC)
    async with AsyncSession(seed_engine) as session:
        await session.execute(
            sa.update(TileRaceEvent)
            .where(TileRaceEvent.is_active.is_(True))
            .values(is_active=False, ends_at=now - timedelta(days=1))
        )
        await session.commit()

    resp = await anon_client.get("/tilerace/active")
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Fog Test"


async def test_active_falls_back_to_a_stopped_event_whatever_the_board_says(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    """Stopping an event is enough to show its recap.

    No team need have reached the finish and no end date need have passed: only
    a finish pad with its `ends_game` trigger on ever sets `is_finished`, so
    hanging the recap on that flag left a raced-out event with nothing to show.
    """
    await _seed_active_event(seed_engine)
    now = datetime.now(UTC)
    async with AsyncSession(seed_engine) as session:
        event = (
            await session.execute(
                sa.select(TileRaceEvent).where(TileRaceEvent.is_active.is_(True))
            )
        ).scalar_one()
        team = (
            await session.execute(
                sa.select(TileRaceTeam).where(TileRaceTeam.event_id == event.id)
            )
        ).scalar_one()
        session.add(
            TileRaceRoll(
                event_id=event.id,
                team_id=team.id,
                dice=[3],
                roll=3,
                new_position=1,
                rolled_by=_VIEWER_ID,
                rolled_at=now,
            )
        )
        event.is_active = False
        event.is_finished = False
        event.ends_at = None
        await session.commit()

    resp = await anon_client.get("/tilerace/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Fog Test"
    assert body["is_active"] is False, "the page needs this to know the race is over"
    assert body["is_finished"] is False


async def test_active_ignores_an_event_that_was_never_rolled_on(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    """A draft must not take the page just because it is not active."""
    await _seed_active_event(seed_engine)
    async with AsyncSession(seed_engine) as session:
        await session.execute(
            sa.update(TileRaceEvent)
            .where(TileRaceEvent.is_active.is_(True))
            .values(is_active=False, is_finished=False, ends_at=None)
        )
        await session.commit()

    resp = await anon_client.get("/tilerace/active")
    assert resp.status_code == 404, resp.text


async def test_signed_in_board_carries_only_the_callers_own_signup(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    accounts = await _seed_active_event(seed_engine)

    resp = await client.get("/tilerace/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["my_signup"]["rsn"] == "viewer"
    assert body["my_signup"]["account_id"] == accounts["viewer"]
    assert body["my_team_id"] == body["teams"][0]["id"]
    assert body["my_signup"]["account_id"] != accounts["teammate"]
    assert str(_TEAMMATE_ID) not in resp.text, "a member's Discord id reached the wire"
    assert "signups" not in body
