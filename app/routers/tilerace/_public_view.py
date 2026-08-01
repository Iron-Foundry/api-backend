from __future__ import annotations

from typing import Any

from app.db.models import TileRaceEvent, TileRaceSignup, TileRaceTeam

from ._serializers import _serialize_summary

PUBLIC_SUMMARY_KEYS = frozenset(
    {
        "id",
        "name",
        "is_active",
        "signups_open",
        "fog_of_war",
        "grid_cols",
        "grid_rows",
        "dice_count",
        "dice_sides",
        "team_size",
        "start_pad",
        "end_pad",
        "is_finished",
        "rolls_paused",
        "winner_team_id",
        "background_url",
        "starts_at",
        "ends_at",
        "created_at",
    }
)

_CELL_GEOMETRY_KEYS = ("cell_x", "cell_y", "path_position")


def fog_limit(teams: list[TileRaceTeam]) -> int:
    return max((t.position for t in teams), default=0)


def mask_cells(
    cells: list[dict[str, Any]], teams: list[TileRaceTeam], fog: bool
) -> list[dict[str, Any]]:
    """Reduce fogged cells to bare geometry before any tile is embedded.

    A hidden cell keeps only its grid coordinates and path step, so its tile,
    its requirement and its modifiers never reach the wire.
    """
    if not fog:
        return list(cells)
    limit = fog_limit(teams)
    masked = []
    for cell in cells:
        position = cell.get("path_position")
        if position is None or position <= limit:
            masked.append(dict(cell))
        else:
            masked.append({key: cell.get(key) for key in _CELL_GEOMETRY_KEYS})
    return masked


def _public_member(signup: TileRaceSignup) -> dict[str, Any]:
    return {"rsn": signup.rsn, "is_captain": signup.is_captain}


def _public_team(team: TileRaceTeam, members: list[TileRaceSignup]) -> dict[str, Any]:
    roster = sorted(
        members, key=lambda s: (not s.is_captain, -s.ranking_score, s.rsn.lower())
    )
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "icon_type": team.icon_type,
        "icon_url": team.icon_url,
        "color": team.color,
        "position": team.position,
        "furthest_position": team.furthest_position,
        "members": [_public_member(s) for s in roster],
    }


def _my_signup(signup: TileRaceSignup) -> dict[str, Any]:
    return {
        "team_id": str(signup.team_id) if signup.team_id else None,
        "account_id": signup.account_id,
        "rsn": signup.rsn,
        "wants_captain": signup.wants_captain,
        "is_captain": signup.is_captain,
        "signed_up_at": signup.signed_up_at.isoformat(),
    }


def public_event(
    event: TileRaceEvent,
    teams: list[TileRaceTeam],
    cells: list[dict[str, Any]],
    rosters: dict[int, list[TileRaceSignup]],
    signups: list[TileRaceSignup],
    viewer_id: int | None,
) -> dict[str, Any]:
    """Build the anonymous-safe view of an event.

    Discord ids, per-team effect state and the roster's Discord/account
    identifiers are omitted. The caller's own signup rides along as
    `my_signup` so the page can offer signup controls without the roster.
    """
    summary = _serialize_summary(event)
    mine = (
        next((s for s in signups if s.discord_user_id == viewer_id), None)
        if viewer_id is not None
        else None
    )
    return {
        **{k: v for k, v in summary.items() if k in PUBLIC_SUMMARY_KEYS},
        "cells": cells,
        "teams": [_public_team(t, rosters.get(t.id, [])) for t in teams],
        "signup_count": len(signups),
        "my_signup": _my_signup(mine) if mine else None,
        "my_team_id": str(mine.team_id) if mine and mine.team_id else None,
    }
