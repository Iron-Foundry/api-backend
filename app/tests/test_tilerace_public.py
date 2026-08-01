from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.routers.tilerace._public_view import (
    PUBLIC_SUMMARY_KEYS,
    fog_limit,
    mask_cells,
    public_event,
)

_NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _event(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": 1,
        "name": "Race",
        "is_active": True,
        "signups_open": False,
        "fog_of_war": True,
        "grid_cols": 10,
        "grid_rows": 6,
        "dice_count": 1,
        "dice_sides": 6,
        "team_size": 5,
        "start_pad": None,
        "end_pad": None,
        "is_finished": False,
        "rolls_paused": False,
        "winner_team_id": None,
        "discord_category_id": 111,
        "discord_captains_role_id": 222,
        "discord_captains_channel_id": 333,
        "discord_submissions_channel_id": 444,
        "discord_permissions": {},
        "background_url": None,
        "starts_at": None,
        "ends_at": None,
        "created_at": _NOW,
        "cells": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _team(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": 7,
        "name": "Reds",
        "slug": "reds",
        "icon_type": "npc",
        "icon_url": "",
        "color": "#f00",
        "position": 3,
        "furthest_position": 3,
        "discord_role_id": 555,
        "discord_text_channel_id": 666,
        "discord_voice_channel_id": 777,
        "pending_effects": {"skip_next": True, "traps_sprung": [12]},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _signup(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "discord_user_id": 900,
        "team_id": 7,
        "account_id": 42,
        "rsn": "Zezima",
        "ranking_score": 1200,
        "wants_captain": True,
        "is_captain": True,
        "added_by_staff": False,
        "signed_up_at": _NOW,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_fog_limit_is_the_furthest_current_position() -> None:
    assert fog_limit([_team(position=3), _team(id=8, position=9)]) == 9
    assert fog_limit([]) == 0


def test_mask_cells_strips_content_beyond_the_fog() -> None:
    cells = [
        {"cell_x": 0, "cell_y": 0, "path_position": 3, "tile_id": "1", "modifiers": []},
        {
            "cell_x": 1,
            "cell_y": 0,
            "path_position": 4,
            "tile_id": "2",
            "modifiers": [{"type": "trap", "dice_count": 1, "dice_sides": 6}],
        },
        {"cell_x": 2, "cell_y": 0, "path_position": None, "tile_id": None},
    ]
    masked = mask_cells(cells, [_team(position=3)], fog=True)
    assert masked[0]["tile_id"] == "1"
    assert masked[1] == {"cell_x": 1, "cell_y": 0, "path_position": 4}
    assert masked[2]["path_position"] is None


def test_mask_cells_passes_everything_when_fog_is_off() -> None:
    cells = [{"cell_x": 0, "cell_y": 0, "path_position": 9, "tile_id": "2"}]
    assert mask_cells(cells, [_team(position=1)], fog=False) == cells


def test_public_event_withholds_discord_ids_and_effects() -> None:
    payload = public_event(
        _event(), [_team()], [], {7: [_signup()]}, [_signup()], viewer_id=None
    )
    assert (
        set(payload)
        - {
            "cells",
            "teams",
            "signup_count",
            "my_signup",
            "my_team_id",
        }
        <= PUBLIC_SUMMARY_KEYS
    )
    assert not [k for k in payload if k.startswith("discord_")]
    assert "signups" not in payload
    team = payload["teams"][0]
    assert not [k for k in team if k.startswith("discord_")]
    assert "pending_effects" not in team


def test_public_event_reduces_the_roster_to_names() -> None:
    payload = public_event(
        _event(), [_team()], [], {7: [_signup()]}, [_signup()], viewer_id=None
    )
    assert payload["teams"][0]["members"] == [{"rsn": "Zezima", "is_captain": True}]
    assert payload["signup_count"] == 1


def test_public_event_hides_other_members_signups_from_a_viewer() -> None:
    mine = _signup(discord_user_id=900)
    theirs = _signup(discord_user_id=901, rsn="Other", is_captain=False)
    payload = public_event(
        _event(), [_team()], [], {7: [mine, theirs]}, [mine, theirs], viewer_id=900
    )
    assert payload["my_signup"]["account_id"] == 42
    assert payload["my_signup"]["rsn"] == "Zezima"
    assert payload["my_team_id"] == "7"
    assert payload["signup_count"] == 2


def test_public_event_gives_an_anonymous_viewer_no_signup() -> None:
    payload = public_event(
        _event(), [_team()], [], {7: [_signup()]}, [_signup()], viewer_id=None
    )
    assert payload["my_signup"] is None
    assert payload["my_team_id"] is None
