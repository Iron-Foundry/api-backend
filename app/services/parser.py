"""Parse OSRS clan broadcast messages into structured event data.

Broadcast messages arrive as CLAN_MESSAGE type with sender == clan name.
All patterns are derived from the standard OSRS clan broadcast formats.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

_IMG_TAG_RE = re.compile(r"<img=\d+>\s*")
_CA_ID_RE = re.compile(r"CA_ID:\d+\|")


def _strip(message: str) -> str:
    """Remove OSRS image tags and CA_ID prefixes before pattern matching."""
    message = _IMG_TAG_RE.sub("", message).strip()
    return _CA_ID_RE.sub("", message).strip()


class BroadcastType(str, Enum):
    LOOT = "loot"
    LEVEL_UP = "level_up"
    XP_MILESTONE = "xp_milestone"
    QUEST = "quest"
    DIARY = "diary"
    COMBAT_ACHIEVEMENT = "combat_achievement"
    PET = "pet"
    NEW_MEMBER = "new_member"
    COLLECTION_LOG = "collection_log"
    LOOT_KEY = "loot_key"
    CLUE_ITEM = "clue_item"
    PK = "pk"
    PERSONAL_BEST = "personal_best"
    LEFT_CLAN = "left_clan"
    EXPELLED = "expelled"
    COFFER_DONATION = "coffer_donation"
    COFFER_WITHDRAWAL = "coffer_withdrawal"
    HCIM_DEATH = "hcim_death"
    LEAGUE_RELIC = "league_relic"
    LEAGUE_RANK = "league_rank"
    LEAGUE_AREA = "league_area"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dataclass
class ParsedLoot:
    player_name: str
    item_name: str
    coin_value: int | None
    source: str | None  # NPC/raid name, None if not present


@dataclass
class ParsedLevelUp:
    player_name: str
    skill: str
    new_level: int  # 99 for "reached the highest level" messages


@dataclass
class ParsedXpMilestone:
    player_name: str
    skill: str
    xp: int


@dataclass
class ParsedAchievement:
    player_name: str
    kind: Literal["quest", "diary", "combat_achievement"]
    name: str
    difficulty: str | None = None  # normalised lowercase; None for quest/diary


@dataclass
class ParsedPet:
    player_name: str


@dataclass
class ParsedNewMember:
    player_name: str
    invited_by: str


@dataclass
class ParsedCollectionLog:
    player_name: str
    item_name: str
    log_slots: int
    log_slots_max: int


@dataclass
class ParsedLootKey:
    player_name: str
    coin_value: int


@dataclass
class ParsedClueItem:
    player_name: str
    item_name: str
    coin_value: int | None


@dataclass
class ParsedPk:
    winner: str
    loser: str
    gp_exchanged: int | None


@dataclass
class ParsedPersonalBest:
    player_name: str
    activity: str
    time_seconds: float
    variant: str | None


@dataclass
class ParsedClanLeave:
    player_name: str
    expelled_by: str | None  # None if player left voluntarily


@dataclass
class ParsedCofferTransaction:
    player_name: str
    amount: int
    is_donation: bool  # False = withdrawal


@dataclass
class ParsedHcimDeath:
    player_name: str


@dataclass
class ParsedLeagueRelic:
    player_name: str
    tier: int


@dataclass
class ParsedLeagueRank:
    player_name: str
    rank: str


@dataclass
class ParsedLeagueArea:
    player_name: str
    area_count: int | None  # None = "final" area


_LOOT_PATTERN = re.compile(
    r"^(?P<player>.+?) received a drop: (?:(?P<quantity>[\d,]+) x )?(?P<item>.+?)"
    r"(?: \((?P<value>[\d,]+) coins\))?(?: from (?P<source>.+?))?\.?$"
)

_RAID_LOOT_PATTERN = re.compile(
    r"^(?P<player>.+?) received special loot from a raid: (?P<item>.+?)\.?$"
)

_LEVEL_IN_PATTERN = re.compile(
    r"^(?P<player>.+?) has reached (?:level (?P<level>\d+)|the highest(?: possible)? level) in (?P<skill>.+?)\.?$"
)

_LEVEL_OF_PATTERN = re.compile(
    r"^(?P<player>.+?) has reached (?:a )?(?:the highest possible )?(?P<skill>.+?) level(?: of)? (?P<level>\d+)[!.]"
)

_XP_MILESTONE_PATTERN = re.compile(
    r"^(?P<player>.+?) has reached (?P<xp>[\d,]+) XP in (?P<skill>.+?)[!.]?$"
)

_QUEST_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed a quest: (?P<name>.+?)\.?$"
)

_DIARY_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed the (?P<name>.+? diary)\.?$"
)

_COMBAT_ACH_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed "
    r"(?:the combat achievement"
    r"|an? (?P<difficulty>easy|medium|hard|elite|master|grandmaster) combat task)"
    r": (?P<name>.+?)\.?$",
    re.IGNORECASE,
)

_COMBAT_TIER_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed all "
    r"(?P<difficulty>easy|medium|hard|elite|master|grandmaster) combat tasks\.?$",
    re.IGNORECASE,
)

_COMBAT_TIER_UNLOCK_PATTERN = re.compile(
    r"^(?P<player>.+?) has unlocked the "
    r"(?P<difficulty>easy|medium|hard|elite|master|grandmaster) tier of rewards from Combat Achievements[!.]?$",
    re.IGNORECASE,
)

_PET_PATTERNS = [
    re.compile(r"^(?P<player>.+?) has a funny feeling like (?:they'?re|he's|she's) being followed"),
    re.compile(
        r"^(?P<player>.+?) feels something weird sneaking into (?:their|his|her) backpack"
    ),
]

_NEW_MEMBER_PATTERN = re.compile(
    r"^(?P<player>.+?) has been invited into the clan by (?P<inviter>.+?)\.?$"
)

_COLLECTION_LOG_PATTERN = re.compile(
    r"^(?P<player>.+?) received a new collection log item: (?P<item>.+?) \((?P<slots>\d+)/(?P<max>\d+)\)"
)

_LOOT_KEY_PATTERN = re.compile(
    r"^(?P<player>.+?) has opened a loot key worth (?P<value>[\d,]+) coins[!.]"
)

_CLUE_ITEM_PATTERN = re.compile(
    r"^(?P<player>.+?) received a clue item: (?P<item>.+?)(?: \((?P<value>[\d,]+) coins\))?\.?$"
)

_PK_WINNER_PATTERN = re.compile(
    r"^(?P<winner>.+?) has defeated (?P<loser>.+?) and received \((?P<gp>[\d,]+) coins\) worth of loot[!.]"
)

_PK_LOSER_PATTERN = re.compile(
    r"^(?P<loser>.+?) has been defeated by (?P<winner>.+?)"
    r"(?:(?: in .+?)?(?: and lost \((?P<gp>[\d,]+) coins\) worth of loot)?)[!.]"
)

_PERSONAL_BEST_PATTERN = re.compile(
    r"^(?P<player>.+?) (?:has )?achieved a new (?P<activity>.+?) "
    r"(?:(?P<variant>Overall|Challenge) )?personal best: (?P<time>[\d:]+(?:\.\d{2})?)$"
)

_LEFT_CLAN_PATTERN = re.compile(r"^(?P<player>.+?) has left the clan\.$")

_EXPELLED_PATTERN = re.compile(
    r"^(?P<mod>.+?) has expelled (?P<player>.+?) from the clan\.$"
)

_COFFER_PATTERN = re.compile(
    r"^(?P<player>.+?) has (?P<action>deposited|withdrawn) (?P<gp>[\d,]+) coins (?:into|from) the coffer\."
)


_HCIM_DEATH_PATTERN = re.compile(
    r"^(?P<player>.+?) has died and lost their Hardcore Ironman status\.$"
)

_LEAGUE_RELIC_PATTERN = re.compile(
    r"^(?P<player>.+?) has unlocked their tier (?P<tier>\d+) League relic!$"
)

_LEAGUE_RANK_PATTERN = re.compile(
    r"^(?P<player>.+?) has earned the (?P<rank>.+?) rank!$"
)

_LEAGUE_AREA_PATTERN = re.compile(
    r"^(?P<player>.+?) has unlocked their (?:(?P<nth>\d+)(?:st|nd|rd|th)|final) League area!$"
)


def _parse_osrs_time(time_str: str) -> float:
    """Convert an OSRS time string (``MM:SS`` or ``H:MM:SS``, optional ``.ss``) to seconds."""
    sub_parts = time_str.split(".")
    sub_seconds = float(f"0.{sub_parts[1]}") if len(sub_parts) > 1 else 0.0
    parts = sub_parts[0].split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1]) + sub_seconds
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + sub_seconds
    return 0.0


def classify(message: str) -> BroadcastType:
    """Return the broadcast type for a clan broadcast (sender == clan name)."""
    message = _strip(message)
    if _LOOT_PATTERN.match(message) or _RAID_LOOT_PATTERN.match(message):
        return BroadcastType.LOOT
    if _LEVEL_IN_PATTERN.match(message) or _LEVEL_OF_PATTERN.match(message):
        return BroadcastType.LEVEL_UP
    if _XP_MILESTONE_PATTERN.match(message):
        return BroadcastType.XP_MILESTONE
    if _QUEST_PATTERN.match(message):
        return BroadcastType.QUEST
    if _DIARY_PATTERN.match(message):
        return BroadcastType.DIARY
    if (
        _COMBAT_ACH_PATTERN.match(message)
        or _COMBAT_TIER_PATTERN.match(message)
        or _COMBAT_TIER_UNLOCK_PATTERN.match(message)
    ):
        return BroadcastType.COMBAT_ACHIEVEMENT
    if any(p.match(message) for p in _PET_PATTERNS):
        return BroadcastType.PET
    if _NEW_MEMBER_PATTERN.match(message):
        return BroadcastType.NEW_MEMBER
    if _COLLECTION_LOG_PATTERN.match(message):
        return BroadcastType.COLLECTION_LOG
    if _LOOT_KEY_PATTERN.match(message):
        return BroadcastType.LOOT_KEY
    if _CLUE_ITEM_PATTERN.match(message):
        return BroadcastType.CLUE_ITEM
    if _PK_WINNER_PATTERN.match(message) or _PK_LOSER_PATTERN.match(message):
        return BroadcastType.PK
    if _PERSONAL_BEST_PATTERN.match(message):
        return BroadcastType.PERSONAL_BEST
    if _LEFT_CLAN_PATTERN.match(message):
        return BroadcastType.LEFT_CLAN
    if _EXPELLED_PATTERN.match(message):
        return BroadcastType.EXPELLED
    if m := _COFFER_PATTERN.match(message):
        return (
            BroadcastType.COFFER_DONATION
            if m.group("action") == "deposited"
            else BroadcastType.COFFER_WITHDRAWAL
        )
    if _HCIM_DEATH_PATTERN.match(message):
        return BroadcastType.HCIM_DEATH
    if _LEAGUE_RELIC_PATTERN.match(message):
        return BroadcastType.LEAGUE_RELIC
    if _LEAGUE_RANK_PATTERN.match(message):
        return BroadcastType.LEAGUE_RANK
    if _LEAGUE_AREA_PATTERN.match(message):
        return BroadcastType.LEAGUE_AREA
    return BroadcastType.UNKNOWN


def parse_loot(message: str) -> ParsedLoot | None:
    message = _strip(message)
    if m := _LOOT_PATTERN.match(message):
        raw_value = m.group("value")
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
            source=m.group("source") or "Generic PVM",
        )
    if m := _RAID_LOOT_PATTERN.match(message):
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=None,
            source="raid",
        )
    return None


def parse_level_up(message: str) -> ParsedLevelUp | None:
    message = _strip(message)
    if m := _LEVEL_IN_PATTERN.match(message):
        level_str = m.group("level")
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(level_str) if level_str else 99,
        )
    if m := _LEVEL_OF_PATTERN.match(message):
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(m.group("level")),
        )
    return None


def parse_xp_milestone(message: str) -> ParsedXpMilestone | None:
    message = _strip(message)
    if m := _XP_MILESTONE_PATTERN.match(message):
        return ParsedXpMilestone(
            player_name=m.group("player"),
            skill=m.group("skill"),
            xp=int(m.group("xp").replace(",", "")),
        )
    return None


def parse_achievement(message: str) -> ParsedAchievement | None:
    message = _strip(message)
    if m := _QUEST_PATTERN.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="quest", name=m.group("name")
        )
    if m := _DIARY_PATTERN.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="diary", name=m.group("name")
        )
    if m := _COMBAT_ACH_PATTERN.match(message):
        diff = m.group("difficulty")
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=m.group("name"),
            difficulty=diff.lower() if diff else None,
        )
    if m := _COMBAT_TIER_PATTERN.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    if m := _COMBAT_TIER_UNLOCK_PATTERN.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    return None


def parse_pet(message: str) -> ParsedPet | None:
    message = _strip(message)
    for pattern in _PET_PATTERNS:
        if m := pattern.match(message):
            return ParsedPet(player_name=m.group("player"))
    return None


def parse_new_member(message: str) -> ParsedNewMember | None:
    message = _strip(message)
    if m := _NEW_MEMBER_PATTERN.match(message):
        return ParsedNewMember(
            player_name=m.group("player"), invited_by=m.group("inviter")
        )
    return None


def parse_collection_log(message: str) -> ParsedCollectionLog | None:
    message = _strip(message)
    if m := _COLLECTION_LOG_PATTERN.match(message):
        return ParsedCollectionLog(
            player_name=m.group("player"),
            item_name=m.group("item"),
            log_slots=int(m.group("slots")),
            log_slots_max=int(m.group("max")),
        )
    return None


def parse_loot_key(message: str) -> ParsedLootKey | None:
    message = _strip(message)
    if m := _LOOT_KEY_PATTERN.match(message):
        return ParsedLootKey(
            player_name=m.group("player"),
            coin_value=int(m.group("value").replace(",", "")),
        )
    return None


def parse_clue_item(message: str) -> ParsedClueItem | None:
    message = _strip(message)
    if m := _CLUE_ITEM_PATTERN.match(message):
        raw_value = m.group("value")
        return ParsedClueItem(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
        )
    return None


def parse_pk(message: str) -> ParsedPk | None:
    message = _strip(message)
    if m := _PK_WINNER_PATTERN.match(message):
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(m.group("gp").replace(",", "")),
        )
    if m := _PK_LOSER_PATTERN.match(message):
        raw_gp = m.group("gp")
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(raw_gp.replace(",", "")) if raw_gp else None,
        )
    return None


def parse_personal_best(message: str) -> ParsedPersonalBest | None:
    message = _strip(message)
    if m := _PERSONAL_BEST_PATTERN.match(message):
        return ParsedPersonalBest(
            player_name=m.group("player"),
            activity=m.group("activity"),
            time_seconds=_parse_osrs_time(m.group("time")),
            variant=m.group("variant"),
        )
    return None


def parse_clan_leave(message: str) -> ParsedClanLeave | None:
    message = _strip(message)
    if m := _LEFT_CLAN_PATTERN.match(message):
        return ParsedClanLeave(player_name=m.group("player"), expelled_by=None)
    if m := _EXPELLED_PATTERN.match(message):
        return ParsedClanLeave(
            player_name=m.group("player"), expelled_by=m.group("mod")
        )
    return None


def parse_coffer_transaction(message: str) -> ParsedCofferTransaction | None:
    message = _strip(message)
    if m := _COFFER_PATTERN.match(message):
        return ParsedCofferTransaction(
            player_name=m.group("player"),
            amount=int(m.group("gp").replace(",", "")),
            is_donation=m.group("action") == "deposited",
        )
    return None


def parse_hcim_death(message: str) -> ParsedHcimDeath | None:
    message = _strip(message)
    if m := _HCIM_DEATH_PATTERN.match(message):
        return ParsedHcimDeath(player_name=m.group("player"))
    return None


def parse_league_relic(message: str) -> ParsedLeagueRelic | None:
    message = _strip(message)
    if m := _LEAGUE_RELIC_PATTERN.match(message):
        return ParsedLeagueRelic(player_name=m.group("player"), tier=int(m.group("tier")))
    return None


def parse_league_rank(message: str) -> ParsedLeagueRank | None:
    message = _strip(message)
    if m := _LEAGUE_RANK_PATTERN.match(message):
        return ParsedLeagueRank(player_name=m.group("player"), rank=m.group("rank"))
    return None


def parse_league_area(message: str) -> ParsedLeagueArea | None:
    message = _strip(message)
    if m := _LEAGUE_AREA_PATTERN.match(message):
        nth = m.group("nth")
        return ParsedLeagueArea(
            player_name=m.group("player"),
            area_count=int(nth) if nth else None,
        )
    return None
