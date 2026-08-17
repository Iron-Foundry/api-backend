from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.routers.tilerace._public_view import PUBLIC_SUMMARY_KEYS
from app.routers.tilerace._recap import (
    cleared,
    countable,
    recap_payload,
    removed_racers,
    surviving_ids,
)

_NOW = datetime(2026, 7, 2, 12, tzinfo=UTC)
_KEPT = 900
_REMOVED = 901


def _event(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": 1,
        "name": "Cursed Cliffs",
        "is_active": False,
        "signups_open": False,
        "fog_of_war": True,
        "grid_cols": 10,
        "grid_rows": 6,
        "dice_count": 1,
        "dice_sides": 6,
        "team_size": 5,
        "start_pad": None,
        "end_pad": None,
        "is_finished": True,
        "rolls_paused": False,
        "winner_team_id": 7,
        "discord_category_id": 111,
        "discord_captains_role_id": 222,
        "discord_captains_channel_id": 333,
        "discord_submissions_channel_id": 444,
        "discord_permissions": {},
        "background_url": None,
        "starts_at": _NOW,
        "ends_at": _NOW,
        "created_at": _NOW,
        "cells": [
            {"cell_x": 0, "cell_y": 0, "path_position": 1},
            {"cell_x": 1, "cell_y": 0, "path_position": 2},
            {"cell_x": 2, "cell_y": 0, "path_position": None},
        ],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _team(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": 7,
        "name": "Iron Kings",
        "slug": "iron-kings",
        "icon_type": "npc",
        "icon_url": "",
        "color": "#ef4444",
        "position": 12,
        "furthest_position": 0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _signup(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "discord_user_id": _KEPT,
        "team_id": 7,
        "rsn": "Zezima",
        "ranking_score": 1200,
        "is_captain": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _submission(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "team_id": 7,
        "path_position": 3,
        "discord_user_id": _KEPT,
        "status": "approved",
        "submitted_at": _NOW,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _roll(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "team_id": 7,
        "new_position": 4,
        "rolled_at": _NOW,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _completion(**overrides: Any) -> Any:
    base: dict[str, Any] = {"team_id": 7, "path_position": 3, "status": "approved"}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_surviving_ids_are_the_rows_still_on_the_roster() -> None:
    assert surviving_ids([_signup(), _signup(discord_user_id=902)]) == {_KEPT, 902}
    assert surviving_ids([]) == set()


def test_countable_drops_a_removed_racers_submissions() -> None:
    subs = [_submission(), _submission(discord_user_id=_REMOVED)]
    assert countable(subs, {_KEPT}) == [subs[0]]
    assert removed_racers(subs, {_KEPT}) == 1


def test_removed_racers_counts_each_author_once() -> None:
    subs = [
        _submission(discord_user_id=_REMOVED),
        _submission(discord_user_id=_REMOVED, path_position=4),
    ]
    assert removed_racers(subs, {_KEPT}) == 1


def test_cleared_counts_claimed_and_approved_but_not_rejected() -> None:
    rows = [
        _completion(status="approved"),
        _completion(path_position=4, status="claimed"),
        _completion(path_position=5, status="rejected"),
    ]
    assert cleared(rows) == 2


def _payload(**overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "event": _event(),
        "teams": [_team()],
        "signups": [_signup()],
        "rolls": [_roll()],
        "completions": [_completion()],
        "submissions": [_submission()],
        "next_event": None,
    }
    args.update(overrides)
    return recap_payload(**args)


def test_recap_withholds_discord_ids_and_the_board() -> None:
    payload = _payload()

    assert set(payload["event"]) - {"path_length"} <= PUBLIC_SUMMARY_KEYS
    assert not [k for k in payload["event"] if k.startswith("discord_")]
    assert "cells" not in payload["event"]
    racer = payload["teams"][0]["roster"][0]
    assert set(racer) == {"rsn", "is_captain", "approved", "rejected", "tiles_proved"}


def test_recap_path_length_ignores_off_path_cells() -> None:
    assert _payload()["event"]["path_length"] == 2


def test_recap_totals_exclude_a_removed_racer() -> None:
    payload = _payload(
        submissions=[
            _submission(),
            _submission(discord_user_id=_REMOVED, path_position=4),
            _submission(status="rejected", path_position=5),
            _submission(status="pending", path_position=6),
        ]
    )

    totals = payload["totals"]
    assert totals["submitted"] == 3
    assert totals["approved"] == 1
    assert totals["rejected"] == 1
    assert totals["unreviewed"] == 1
    assert totals["removed_racers"] == 1
    assert totals["racers"] == 1


def test_recap_racer_counts_only_their_own_proofs() -> None:
    payload = _payload(
        signups=[
            _signup(),
            _signup(discord_user_id=902, rsn="Kaelith", is_captain=False),
        ],
        submissions=[
            _submission(),
            _submission(path_position=4),
            _submission(discord_user_id=902, path_position=5),
            _submission(discord_user_id=902, path_position=5, status="rejected"),
        ],
    )

    captain, other = payload["teams"][0]["roster"]
    assert captain["rsn"] == "Zezima" and captain["is_captain"] is True
    assert captain["approved"] == 2 and captain["tiles_proved"] == 2
    assert other["approved"] == 1 and other["rejected"] == 1
    assert other["tiles_proved"] == 1


def test_recap_series_are_ordered_and_bucketed_by_day() -> None:
    later = datetime(2026, 7, 3, 9, tzinfo=UTC)
    payload = _payload(
        rolls=[_roll(new_position=9, rolled_at=later), _roll(new_position=4)],
        submissions=[
            _submission(),
            _submission(path_position=4, submitted_at=later),
            _submission(path_position=5, status="rejected", submitted_at=later),
        ],
    )

    team = payload["teams"][0]
    assert [p["position"] for p in team["position_series"]] == [4, 9]
    assert team["submission_series"] == [
        {"day": "2026-07-02", "approved": 1, "rejected": 0, "unreviewed": 0},
        {"day": "2026-07-03", "approved": 1, "rejected": 1, "unreviewed": 0},
    ]


def test_recap_orders_teams_as_final_standings() -> None:
    payload = _payload(
        teams=[
            _team(id=7, name="Iron Kings", position=12),
            _team(id=8, name="Blue Vipers", slug="blue-vipers", position=30),
            _team(id=9, name="Gold Krakens", slug="gold-krakens", position=30),
        ],
        completions=[
            _completion(team_id=9),
            _completion(team_id=9, path_position=4),
            _completion(team_id=8),
        ],
    )

    assert [t["name"] for t in payload["teams"]] == [
        "Gold Krakens",
        "Blue Vipers",
        "Iron Kings",
    ]


def test_recap_furthest_position_keeps_a_rolled_back_teams_best() -> None:
    payload = _payload(teams=[_team(position=12, furthest_position=27)])

    team = payload["teams"][0]
    assert team["position"] == 12
    assert team["furthest_position"] == 27


def test_recap_carries_the_next_event_when_one_is_scheduled() -> None:
    nxt = {"id": "2", "name": "Frostfall", "is_active": False, "starts_at": None}

    assert _payload(next_event=nxt)["next_event"] == nxt
    assert _payload()["next_event"] is None
