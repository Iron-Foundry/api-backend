"""The api -> runelite clan-chat relay, end to end over a real WebSocket.

A dispatch POST must reach a connected WebSocket client as a wrapped
``ToClanChat`` frame. Both the WS auth and the dispatch auth resolve the same
api-key-bearing User row from the real database.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.datastructures import State
from starlette.testclient import TestClient

pytestmark = pytest.mark.integration

_API_KEY = "integration-test-key"
_GUILD_ID = 555000111
_DISCORD_USER_ID = 900900900


def _seed_user(db_url: str) -> None:
    async def _run() -> None:
        engine = create_async_engine(db_url)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            from app.db.models import User

            now = datetime.now(UTC)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add(
                    User(
                        discord_user_id=_DISCORD_USER_ID,
                        discord_username="clanchat-tester",
                        guild_id=_GUILD_ID,
                        api_key=_API_KEY,
                        key_is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_dispatch_reaches_connected_ws(db_url: str) -> None:
    _seed_user(db_url)

    from app.main import app as real_app

    # TestClient drives the app on its own event loop, so it has to boot its own
    # lifespan - the session-scoped one's engine and Valkey client are bound to
    # the suite's loop and cannot be reached from here. Both lifespans write to
    # the same `app.state`, so this one gets a scratch copy that is thrown away
    # afterwards, leaving the shared app untouched for the tests that follow.
    shared_state = real_app.state
    real_app.state = State(
        {"endpoint_metrics_collector": shared_state.endpoint_metrics_collector}
    )
    try:
        _dispatch_and_assert(real_app)
    finally:
        real_app.state = shared_state


def _dispatch_and_assert(real_app: FastAPI) -> None:
    with (
        TestClient(real_app, headers={"verification-code": _API_KEY}) as tc,
        tc.websocket_connect("/ccdispatch") as ws,
    ):
        hello = ws.receive_json()
        assert hello["message_type"] == "ToClanChat"
        assert hello["message"]["sender"] == "System"

        resp = tc.post(
            "/ccdispatch",
            headers={"verification-code": _API_KEY},
            json={"sender": "Zezima", "message": "hello clan", "rank": "Owner"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        frame = ws.receive_json()
        assert frame["message_type"] == "ToClanChat"
        assert frame["message"]["sender"] == "Zezima"
        assert frame["message"]["message"] == "hello clan"
        assert frame["message"]["rank"] == "Owner"
