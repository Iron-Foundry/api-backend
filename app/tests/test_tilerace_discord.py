from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.db.models import TileRaceEvent, TileRaceTeam
from app.routers.tilerace._discord_payload import COMMAND_CHANNEL, build_command

_FIXTURE = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "tilerace_discord.json").read_text()
)


def _event(**overrides: Any) -> TileRaceEvent:
    base: dict[str, Any] = {
        "id": 12,
        "name": "Summer Tile Race",
        "discord_category_id": None,
        "discord_captains_role_id": None,
        "discord_captains_channel_id": None,
    }
    return TileRaceEvent(**{**base, **overrides})


def _team(**overrides: Any) -> TileRaceTeam:
    base: dict[str, Any] = {
        "id": 31,
        "name": "Abyssal Ashes",
        "slug": "abyssal-ashes",
        "discord_role_id": None,
        "discord_text_channel_id": None,
        "discord_voice_channel_id": None,
    }
    return TileRaceTeam(**{**base, **overrides})


def _load_event(mock_session: MagicMock, event: TileRaceEvent | None) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = event
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    mock_session.execute.return_value = result


async def test_setup_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tilerace/events/9999/discord/setup")
    assert resp.status_code == 401


async def test_setup_event_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/tilerace/events/9999/discord/setup")
    assert resp.status_code == 404


async def test_setup_rejected_when_already_provisioned(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load_event(mock_session, _event(discord_category_id=900))
    resp = await staff_client.post("/tilerace/events/12/discord/setup")
    assert resp.status_code == 409
    assert "already exist" in resp.json()["detail"]


async def test_setup_rejected_without_teams(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load_event(mock_session, _event())
    resp = await staff_client.post("/tilerace/events/12/discord/setup")
    assert resp.status_code == 409
    assert "Generate teams" in resp.json()["detail"]


async def test_teardown_rejected_when_nothing_provisioned(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load_event(mock_session, _event())
    resp = await staff_client.post("/tilerace/events/12/discord/teardown")
    assert resp.status_code == 409


async def test_sync_publishes_on_the_contract_channel(
    staff_client: AsyncClient, mock_session: MagicMock, mock_valkey: AsyncMock
) -> None:
    _load_event(mock_session, _event(discord_category_id=900))
    resp = await staff_client.post("/tilerace/events/12/discord/sync")
    assert resp.status_code == 200
    channel, payload = mock_valkey.publish.call_args.args
    assert channel == COMMAND_CHANNEL == _FIXTURE["channel"]
    assert json.loads(payload)["action"] == "sync"


async def test_result_writes_every_id_back(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    event = _event()
    team = _team()
    result = MagicMock()
    result.scalar_one_or_none.return_value = event
    result.scalars.return_value.all.return_value = [team]
    mock_session.execute.return_value = result

    resp = await anon_client.post(
        "/tilerace/events/12/discord/result", json=_FIXTURE["result"]
    )
    assert resp.status_code == 200
    assert resp.json()["teams_recorded"] == 1
    assert event.discord_category_id == _FIXTURE["result"]["category_id"]
    assert event.discord_captains_role_id == _FIXTURE["result"]["captains_role_id"]
    assert team.discord_role_id == _FIXTURE["result"]["teams"][0]["role_id"]
    assert (
        team.discord_voice_channel_id
        == (_FIXTURE["result"]["teams"][0]["voice_channel_id"])
    )


async def test_teardown_result_clears_every_id(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    event = _event(
        discord_category_id=900,
        discord_captains_role_id=901,
        discord_captains_channel_id=902,
    )
    team = _team(
        discord_role_id=903, discord_text_channel_id=904, discord_voice_channel_id=905
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = event
    result.scalars.return_value.all.return_value = [team]
    mock_session.execute.return_value = result

    resp = await anon_client.post(
        "/tilerace/events/12/discord/result", json=_FIXTURE["teardown_result"]
    )
    assert resp.status_code == 200
    assert event.discord_category_id is None
    assert team.discord_role_id is None
    assert team.discord_text_channel_id is None
    assert team.discord_voice_channel_id is None


async def test_roster_edit_syncs_when_provisioned(
    staff_client: AsyncClient, mock_session: MagicMock, mock_valkey: AsyncMock
) -> None:
    """A roster move has to reach Discord or a removed member keeps their role."""
    entry = MagicMock(id=1, team_id=None, is_captain=False, rsn="p", event_id=12)
    result = MagicMock()
    result.scalar_one_or_none.return_value = _event(discord_category_id=900)
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = entry
    mock_session.execute.return_value = result
    mock_session.delete = AsyncMock()

    with patch(
        "app.routers.tilerace.roster.entry_or_404", new=AsyncMock(return_value=entry)
    ):
        resp = await staff_client.delete("/tilerace/events/12/roster/777")

    assert resp.status_code == 200
    channels = [c.args[0] for c in mock_valkey.publish.call_args_list]
    assert COMMAND_CHANNEL in channels


async def test_no_sync_when_the_event_has_no_channels(
    staff_client: AsyncClient, mock_session: MagicMock, mock_valkey: AsyncMock
) -> None:
    entry = MagicMock(id=1, team_id=None, is_captain=False, rsn="p", event_id=12)
    result = MagicMock()
    result.scalar_one_or_none.return_value = _event()
    result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = result
    mock_session.delete = AsyncMock()

    with patch(
        "app.routers.tilerace.roster.entry_or_404", new=AsyncMock(return_value=entry)
    ):
        resp = await staff_client.delete("/tilerace/events/12/roster/777")

    assert resp.status_code == 200
    mock_valkey.publish.assert_not_called()


async def test_deleting_a_team_removes_its_discord_objects(
    staff_client: AsyncClient, mock_session: MagicMock, mock_valkey: AsyncMock
) -> None:
    team = _team(
        discord_role_id=904, discord_text_channel_id=905, discord_voice_channel_id=906
    )
    result = MagicMock()
    result.scalar_one_or_none.side_effect = [
        team,
        _event(discord_category_id=900),
        _event(discord_category_id=900),
    ]
    result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = result
    mock_session.delete = AsyncMock()

    resp = await staff_client.delete("/tilerace/events/12/teams/31")
    assert resp.status_code == 200

    payloads = [json.loads(c.args[1]) for c in mock_valkey.publish.call_args_list]
    removal = next(p for p in payloads if p["action"] == "teardown_team")
    assert removal["team"]["role_id"] == "904"
    assert removal["team"]["voice_channel_id"] == "906"


async def test_command_matches_the_published_contract(
    mock_session: MagicMock,
) -> None:
    signup = SimpleNamespace(
        discord_user_id=111222333444555666, team_id=31, is_captain=True
    )
    other = SimpleNamespace(
        discord_user_id=222333444555666777, team_id=31, is_captain=False
    )
    result = MagicMock()
    result.scalars.return_value.all.side_effect = [
        [_team()],
        [signup],
        [signup, other],
    ]
    mock_session.execute.return_value = result

    command = await build_command(mock_session, _event(), "setup")
    assert command.keys() == _FIXTURE["command"].keys()
    assert command == _FIXTURE["command"]
