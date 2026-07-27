"""Tests for clan broadcast message parsing."""

from __future__ import annotations

import pytest

from app.services.parser import (
    BroadcastType,
    classify,
    parse_achievement,
    parse_league_area,
    parse_league_rank,
    parse_league_relic,
    parse_personal_best,
)

# ---------------------------------------------------------------------------
# Combat achievements - individual tasks
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
        (
            "X has completed a medium combat task: Task Name.",
            "X",
            "medium",
            "Task Name",
        ),
        ("X has completed a hard combat task: Task Name.", "X", "hard", "Task Name"),
        ("X has completed an elite combat task: Task Name.", "X", "elite", "Task Name"),
        (
            "X has completed a master combat task: Task Name.",
            "X",
            "master",
            "Task Name",
        ),
        (
            "X has completed a grandmaster combat task: Task Name.",
            "X",
            "grandmaster",
            "Task Name",
        ),
        # Case-insensitive difficulty
        ("X has completed an Easy combat task: Task.", "X", "easy", "Task"),
        ("X has completed an Elite combat task: Task.", "X", "elite", "Task"),
        (
            "X has completed a Grandmaster combat task: Task.",
            "X",
            "grandmaster",
            "Task",
        ),
        # Legacy format - no difficulty
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


# ---------------------------------------------------------------------------
# League events
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,player,tier",
    [
        ("<img=22> ImNotCreg has unlocked their tier 2 League relic!", "ImNotCreg", 2),
        (
            "<img=22> cardoorvis has unlocked their tier 3 League relic!",
            "cardoorvis",
            3,
        ),
        (
            "<img=22> ImaPixelLoL has unlocked their tier 4 League relic!",
            "ImaPixelLoL",
            4,
        ),
        ("<img=22> Meymer has unlocked their tier 8 League relic!", "Meymer", 8),
    ],
)
def test_parse_league_relic(message: str, player: str, tier: int) -> None:
    result = parse_league_relic(message)
    assert result is not None
    assert result.player_name == player
    assert result.tier == tier


@pytest.mark.parametrize(
    "message",
    [
        "<img=22> ImNotCreg has unlocked their tier 2 League relic!",
        "<img=22> Meymer has unlocked their tier 8 League relic!",
    ],
)
def test_classify_league_relic(message: str) -> None:
    assert classify(message) == BroadcastType.LEAGUE_RELIC


@pytest.mark.parametrize(
    "message,player,rank",
    [
        ("<img=22> Railroaded has earned the Iron rank!", "Railroaded", "Iron"),
        ("<img=22> Hard Wire has earned the Iron rank!", "Hard Wire", "Iron"),
        ("<img=22> Recurrsion has earned the Mithril rank!", "Recurrsion", "Mithril"),
        ("<img=22> Gra3ff has earned the Dragon rank!", "Gra3ff", "Dragon"),
    ],
)
def test_parse_league_rank(message: str, player: str, rank: str) -> None:
    result = parse_league_rank(message)
    assert result is not None
    assert result.player_name == player
    assert result.rank == rank


@pytest.mark.parametrize(
    "message",
    [
        "<img=22> Railroaded has earned the Iron rank!",
        "<img=22> Hard Wire has earned the Iron rank!",
        "<img=22> Gra3ff has earned the Dragon rank!",
    ],
)
def test_classify_league_rank(message: str) -> None:
    assert classify(message) == BroadcastType.LEAGUE_RANK


@pytest.mark.parametrize(
    "message,player,area_count",
    [
        ("<img=22> AZ 5 Pets has unlocked their 4th League area!", "AZ 5 Pets", 4),
        ("<img=22> Fe Gate has unlocked their final League area!", "Fe Gate", None),
        ("<img=22> UIM HAM has unlocked their 2nd League area!", "UIM HAM", 2),
        (
            "<img=22> The Mail Man has unlocked their 2nd League area!",
            "The Mail Man",
            2,
        ),
        ("<img=22> X has unlocked their 1st League area!", "X", 1),
        ("<img=22> X has unlocked their 3rd League area!", "X", 3),
    ],
)
def test_parse_league_area(message: str, player: str, area_count: int | None) -> None:
    result = parse_league_area(message)
    assert result is not None
    assert result.player_name == player
    assert result.area_count == area_count


@pytest.mark.parametrize(
    "message",
    [
        "<img=22> AZ 5 Pets has unlocked their 4th League area!",
        "<img=22> Fe Gate has unlocked their final League area!",
        "<img=22> The Mail Man has unlocked their 2nd League area!",
    ],
)
def test_classify_league_area(message: str) -> None:
    assert classify(message) == BroadcastType.LEAGUE_AREA
