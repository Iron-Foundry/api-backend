"""Aggregate one finished event into the public recap shape.

Everything here is derived from rows the caller may already see on the board,
reduced to counts and series so no proof URL, review note, thread or Discord id
can reach an anonymous viewer. A participant removed from the roster during the
event keeps their rows in the database but drops out of every count: only a
surviving ``tilerace_signups`` row makes a submission countable.
"""

from __future__ import annotations

from typing import Any

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceSubmission,
    TileRaceTeam,
)

from ._public_view import PUBLIC_SUMMARY_KEYS
from ._serializers import _serialize_summary, roster_order

CLEARED_STATUSES = frozenset({"claimed", "approved"})
_VERDICTS = ("submitted", "approved", "rejected", "unreviewed")


def surviving_ids(signups: list[TileRaceSignup]) -> set[int]:
    """Discord ids still on the roster when the event closed."""
    return {s.discord_user_id for s in signups}


def countable(
    submissions: list[TileRaceSubmission], surviving: set[int]
) -> list[TileRaceSubmission]:
    """Submissions whose author is still on the roster."""
    return [s for s in submissions if s.discord_user_id in surviving]


def removed_participants(
    submissions: list[TileRaceSubmission], surviving: set[int]
) -> int:
    """How many distinct authors were removed, so the drop can be stated."""
    return len(
        {s.discord_user_id for s in submissions if s.discord_user_id not in surviving}
    )


def _verdicts(submissions: list[TileRaceSubmission]) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(_VERDICTS, 0)
    counts["submitted"] = len(submissions)
    for s in submissions:
        key = s.status if s.status in counts else "unreviewed"
        counts[key] += 1
    return counts


def _daily(submissions: list[TileRaceSubmission]) -> list[dict[str, Any]]:
    days: dict[str, dict[str, int]] = {}
    for s in submissions:
        day = s.submitted_at.date().isoformat()
        row = days.setdefault(day, {"approved": 0, "rejected": 0, "unreviewed": 0})
        row[s.status if s.status in row else "unreviewed"] += 1
    return [{"day": day, **days[day]} for day in sorted(days)]


def _participant(
    signup: TileRaceSignup, submissions: list[TileRaceSubmission]
) -> dict[str, Any]:
    mine = [s for s in submissions if s.discord_user_id == signup.discord_user_id]
    counts = _verdicts(mine)
    return {
        "rsn": signup.rsn,
        "is_captain": signup.is_captain,
        "approved": counts["approved"],
        "rejected": counts["rejected"],
        "tiles_proven": len({s.path_position for s in mine if s.status == "approved"}),
    }


def cleared(completions: list[TileRaceCompletion]) -> int:
    """Tiles a team proved: claimed or approved, never rejected."""
    return len([c for c in completions if c.status in CLEARED_STATUSES])


def team_recap(
    team: TileRaceTeam,
    roster: list[TileRaceSignup],
    rolls: list[TileRaceRoll],
    completions: list[TileRaceCompletion],
    submissions: list[TileRaceSubmission],
) -> dict[str, Any]:
    """One team's standing, per-participant counts and two time series."""
    ordered = sorted(rolls, key=lambda r: r.rolled_at)
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "icon_type": team.icon_type,
        "icon_url": team.icon_url,
        "color": team.color,
        "position": team.position,
        "furthest_position": max(team.position, team.furthest_position),
        "tiles_cleared": cleared(completions),
        "rolls": len(rolls),
        **_verdicts(submissions),
        "roster": [_participant(s, submissions) for s in roster_order(roster)],
        "position_series": [
            {"at": r.rolled_at.isoformat(), "position": r.new_position} for r in ordered
        ],
        "submission_series": _daily(submissions),
    }


def _path_length(event: TileRaceEvent) -> int:
    return len([c for c in (event.cells or []) if c.get("path_position") is not None])


def _bucket(rows: list[Any]) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.team_id, []).append(row)
    return grouped


def recap_payload(
    event: TileRaceEvent,
    teams: list[TileRaceTeam],
    signups: list[TileRaceSignup],
    rolls: list[TileRaceRoll],
    completions: list[TileRaceCompletion],
    submissions: list[TileRaceSubmission],
    next_event: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the anonymous-safe recap, teams ordered as final standings."""
    surviving = surviving_ids(signups)
    kept = countable(submissions, surviving)
    rosters = _bucket([s for s in signups if s.team_id is not None])
    roll_map, completion_map, submission_map = (
        _bucket(rolls),
        _bucket(completions),
        _bucket(kept),
    )
    summary = _serialize_summary(event)
    entries = [
        team_recap(
            t,
            rosters.get(t.id, []),
            roll_map.get(t.id, []),
            completion_map.get(t.id, []),
            submission_map.get(t.id, []),
        )
        for t in teams
    ]
    entries.sort(key=lambda e: (-e["position"], -e["tiles_cleared"], e["name"]))
    return {
        "event": {
            **{k: v for k, v in summary.items() if k in PUBLIC_SUMMARY_KEYS},
            "path_length": _path_length(event),
        },
        "next_event": next_event,
        "totals": {
            "teams": len(teams),
            "participants": len(signups),
            "removed_participants": removed_participants(submissions, surviving),
            "tiles_cleared": sum(e["tiles_cleared"] for e in entries),
            "rolls": len(rolls),
            **_verdicts(kept),
        },
        "teams": entries,
    }
