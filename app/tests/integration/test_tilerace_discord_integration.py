"""Real Postgres + real Valkey: the tile race Discord seam under a live event.

The interconnect is a pubsub channel, so the only honest check is to subscribe
to it the way discord-server does and watch what actually lands there. Guards
the property a live event depends on: a permission toggle publishes a *sync*
carrying the existing channel ids, never a teardown or a rebuild.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from valkey.asyncio import Valkey

from app.db.models import TileRaceEvent, TileRaceSignup, TileRaceTeam

pytestmark = pytest.mark.integration

_FIXTURE = json.loads(
    (Path(__file__).parents[4] / "fixtures" / "tilerace_discord.json").read_text()
)
_CATEGORY_ID = 900000000000000001
_TEXT_CHANNEL_ID = 900000000000000005
_DELIVERY_TIMEOUT_SECONDS = 10


async def _seed_provisioned_event(engine: AsyncEngine) -> int:
    """An event whose channels already exist, mid-race."""
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        event = TileRaceEvent(
            name="Live Tile Race",
            is_active=True,
            cells=[],
            discord_category_id=_CATEGORY_ID,
            discord_captains_role_id=900000000000000002,
            discord_captains_channel_id=900000000000000003,
            discord_permissions={"pin_messages": True},
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        event_id = event.id
        team = TileRaceTeam(
            event_id=event_id,
            name="Abyssal Ashes",
            slug="abyssal-ashes",
            discord_role_id=900000000000000004,
            discord_text_channel_id=_TEXT_CHANNEL_ID,
            discord_voice_channel_id=900000000000000006,
            updated_at=now,
        )
        session.add(team)
        await session.flush()
        session.add(
            TileRaceSignup(
                event_id=event_id,
                team_id=team.id,
                discord_user_id=111222333444555666,
                rsn="captain one",
                ranking_score=500,
                is_captain=True,
                signed_up_at=now,
            )
        )
        await session.commit()
        return event_id


async def _next_command(pubsub: Any) -> dict[str, Any]:
    async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
        while True:
            message = await pubsub.get_message(timeout=1)
            if message and message["type"] == "message":
                return json.loads(message["data"])


async def test_a_toggle_syncs_the_live_event_in_place(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_provisioned_event(seed_engine)
    valkey = Valkey.from_url(os.environ["VALKEY_URI"])
    try:
        async with valkey.pubsub() as pubsub:
            await pubsub.subscribe(_FIXTURE["channel"])
            await pubsub.get_message(timeout=5)

            resp = await staff_client.patch(
                f"/tilerace/events/{event_id}/discord/permissions",
                json={"mention_everyone": True},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["synced"] is True
            command = await _next_command(pubsub)
    finally:
        await valkey.aclose()

    assert command["action"] == "sync", "a toggle must never trigger a rebuild"
    assert command["category_id"] == str(_CATEGORY_ID), (
        "the existing ids must ride along or the bot creates a second category"
    )
    assert command["teams"][0]["text_channel_id"] == str(_TEXT_CHANNEL_ID)
    assert command["permissions"] == {
        **dict.fromkeys(_FIXTURE["permission_toggles"], False),
        "pin_messages": True,
        "mention_everyone": True,
    }


async def test_the_toggle_survives_a_reload_and_reaches_every_later_sync(
    staff_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    """The toggles are state, not a one-shot command: a later roster edit or a
    manual re-sync has to carry them too, or the bot resets the channel."""
    event_id = await _seed_provisioned_event(seed_engine)
    await staff_client.patch(
        f"/tilerace/events/{event_id}/discord/permissions",
        json={"voice_moderation": True},
    )

    detail = await staff_client.get(f"/tilerace/events/{event_id}")
    assert detail.json()["discord_permissions"]["voice_moderation"] is True

    valkey = Valkey.from_url(os.environ["VALKEY_URI"])
    try:
        async with valkey.pubsub() as pubsub:
            await pubsub.subscribe(_FIXTURE["channel"])
            await pubsub.get_message(timeout=5)

            resync = await staff_client.post(
                f"/tilerace/events/{event_id}/discord/sync"
            )
            assert resync.status_code == 200, resync.text
            command = await _next_command(pubsub)
    finally:
        await valkey.aclose()

    assert command["permissions"]["voice_moderation"] is True
    assert command["permissions"]["pin_messages"] is True
