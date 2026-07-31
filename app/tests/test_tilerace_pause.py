from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from httpx import AsyncClient


def _team_then_event(
    mock_session: MagicMock, team: SimpleNamespace, event: SimpleNamespace
) -> None:
    """The roll endpoint locks the team first, then loads the event."""
    result = MagicMock()
    result.scalar_one_or_none.side_effect = [team, event]
    mock_session.execute.return_value = result


def _event(**overrides: object) -> SimpleNamespace:
    base = {
        "id": 12,
        "is_finished": False,
        "rolls_paused": False,
        "cells": [],
        "dice_count": 1,
        "dice_sides": 6,
        "start_pad": None,
        "end_pad": None,
    }
    return SimpleNamespace(**{**base, **overrides})


async def test_paused_event_refuses_a_roll(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    team = SimpleNamespace(id=31, position=0, pending_effects={}, updated_at=None)
    _team_then_event(mock_session, team, _event(rolls_paused=True))
    resp = await auth_client.post("/tilerace/events/12/teams/31/roll")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Rolling is paused."


async def test_finished_still_wins_over_paused(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    team = SimpleNamespace(id=31, position=0, pending_effects={}, updated_at=None)
    _team_then_event(mock_session, team, _event(is_finished=True, rolls_paused=True))
    resp = await auth_client.post("/tilerace/events/12/teams/31/roll")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Game over."


async def test_pause_is_patchable(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    event = _event()
    result = MagicMock()
    result.scalar_one_or_none.return_value = event
    mock_session.execute.return_value = result
    resp = await staff_client.patch("/tilerace/events/12", json={"rolls_paused": True})
    assert resp.status_code == 200
    assert event.rolls_paused is True
