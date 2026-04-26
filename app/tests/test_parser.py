"""Tests for clan broadcast message parsing."""

from __future__ import annotations

import pytest

from app.services.parser import (
    BroadcastType,
    classify,
    parse_achievement,
    parse_personal_best,
)


# ---------------------------------------------------------------------------
# Combat achievements — individual tasks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,player,difficulty,name",
    [
        # Real production messages
        (
            "CA_ID:237|Weedily has completed an elite combat task: Theatre of Blood Veteran. <img=41>",
            "Weedily",
            "elite",
            "Theatre of Blood Veteran",
        ),
        (
            "CA_ID:8|tagga pallen has completed an elite combat task: Perfect Sire. <img=2>",
            "tagga pallen",
            "elite",
            "Perfect Sire",
        ),
        (
            "CA_ID:548|Martyrs has completed an elite combat task: I was here first!. <img=41>",
            "Martyrs",
            "elite",
            "I was here first!",
        ),
        (
            "CA_ID:4|tagga pallen has completed an elite combat task: Respiratory Runner.",
            "tagga pallen",
            "elite",
            "Respiratory Runner",
        ),
        # All difficulty tiers
        ("X has completed an easy combat task: Task Name.", "X", "easy", "Task Name"),
        ("X has completed a medium combat task: Task Name.", "X", "medium", "Task Name"),
        ("X has completed a hard combat task: Task Name.", "X", "hard", "Task Name"),
        ("X has completed an elite combat task: Task Name.", "X", "elite", "Task Name"),
        ("X has completed a master combat task: Task Name.", "X", "master", "Task Name"),
        (
            "X has completed a grandmaster combat task: Task Name.",
            "X",
            "grandmaster",
            "Task Name",
        ),
        # Case-insensitive difficulty
        ("X has completed an Easy combat task: Task.", "X", "easy", "Task"),
        ("X has completed an Elite combat task: Task.", "X", "elite", "Task"),
        ("X has completed a Grandmaster combat task: Task.", "X", "grandmaster", "Task"),
        # Legacy format — no difficulty
        (
            "X has completed the combat achievement: Task Name.",
            "X",
            None,
            "Task Name",
        ),
        # No trailing period
        ("X has completed an elite combat task: Task Name", "X", "elite", "Task Name"),
    ],
)
def test_parse_ca_individual(
    message: str, player: str, difficulty: str | None, name: str
) -> None:
    result = parse_achievement(message)
    assert result is not None
    assert result.kind == "combat_achievement"
    assert result.player_name == player
    assert result.difficulty == difficulty
    assert result.name == name


@pytest.mark.parametrize(
    "message,player,difficulty",
    [
        ("X has completed all easy combat tasks.", "X", "easy"),
        ("X has completed all medium combat tasks.", "X", "medium"),
        ("X has completed all hard combat tasks.", "X", "hard"),
        ("X has completed all elite combat tasks.", "X", "elite"),
        ("X has completed all master combat tasks.", "X", "master"),
        ("X has completed all grandmaster combat tasks.", "X", "grandmaster"),
        # Case-insensitive
        ("X has completed all Grandmaster combat tasks.", "X", "grandmaster"),
        ("X has completed all Easy combat tasks.", "X", "easy"),
    ],
)
def test_parse_ca_tier(message: str, player: str, difficulty: str) -> None:
    result = parse_achievement(message)
    assert result is not None
    assert result.kind == "combat_achievement"
    assert result.player_name == player
    assert result.difficulty == difficulty
    assert result.name == f"{difficulty} tier"


@pytest.mark.parametrize(
    "message",
    [
        "X has completed an elite combat task: Theatre of Blood Veteran. <img=41>",
        "CA_ID:237|X has completed an elite combat task: Name. <img=41>",
        "X has completed all easy combat tasks.",
        "X has completed the combat achievement: Task Name.",
        "X has completed a medium combat task: Task.",
    ],
)
def test_classify_combat_achievement(message: str) -> None:
    assert classify(message) == BroadcastType.COMBAT_ACHIEVEMENT


# ---------------------------------------------------------------------------
# Personal bests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,player,activity,variant,time_seconds",
    [
        # Real production messages
        (
            "Martyrs achieved a new Tombs of Amascut (team size: 2) Expert mode Overall personal best: 28:02.40 <img=2>",
            "Martyrs",
            "Tombs of Amascut (team size: 2) Expert mode",
            "Overall",
            pytest.approx(1682.4),
        ),
        (
            "Martyrs achieved a new Tombs of Amascut (team size: 2) Expert mode Challenge personal best: 24:29.40 <img=2>",
            "Martyrs",
            "Tombs of Amascut (team size: 2) Expert mode",
            "Challenge",
            pytest.approx(1469.4),
        ),
        # Old "has achieved" format still works
        (
            "X has achieved a new Corp Beast personal best: 1:23.40",
            "X",
            "Corp Beast",
            None,
            pytest.approx(83.4),
        ),
        # New "achieved" format, no variant
        (
            "X achieved a new Theatre of Blood personal best: 12:34.00",
            "X",
            "Theatre of Blood",
            None,
            pytest.approx(754.0),
        ),
        # Hours format
        (
            "X achieved a new Inferno personal best: 1:02:34.20",
            "X",
            "Inferno",
            None,
            pytest.approx(3754.2),
        ),
    ],
)
def test_parse_personal_best(
    message: str,
    player: str,
    activity: str,
    variant: str | None,
    time_seconds: float,
) -> None:
    result = parse_personal_best(message)
    assert result is not None
    assert result.player_name == player
    assert result.activity == activity
    assert result.variant == variant
    assert result.time_seconds == time_seconds


@pytest.mark.parametrize(
    "message",
    [
        "Martyrs achieved a new Tombs of Amascut (team size: 2) Expert mode Overall personal best: 28:02.40 <img=2>",
        "X achieved a new Corp Beast personal best: 1:23.40",
        "X has achieved a new Theatre of Blood personal best: 12:34.00",
    ],
)
def test_classify_personal_best(message: str) -> None:
    assert classify(message) == BroadcastType.PERSONAL_BEST
