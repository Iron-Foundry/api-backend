"""Parse OSRS clan broadcast messages into structured event data.

Broadcast messages arrive as CLAN_MESSAGE type with sender == clan name.
All patterns are derived from the standard OSRS clan broadcast formats.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class BroadcastType(str, Enum):
    LOOT = "loot"
    LEVEL_UP = "level_up"
    QUEST = "quest"
    DIARY = "diary"
    COMBAT_ACHIEVEMENT = "combat_achievement"
    PET = "pet"
    NEW_MEMBER = "new_member"
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
class ParsedAchievement:
    player_name: str
    kind: Literal["quest", "diary", "combat_achievement"]
    name: str


@dataclass
class ParsedPet:
    player_name: str


@dataclass
class ParsedNewMember:
    player_name: str
    invited_by: str


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# "PlayerX received a drop: Dragon claws (75,432,000 coins)."
# "PlayerX received a drop: Dragon claws (75,432,000 coins) from Cerberus."
_LOOT_PATTERN = re.compile(
    r"^(?P<player>.+?) received a drop: (?P<item>.+?) \((?P<value>[\d,]+) coins\)"
    r"(?: from (?P<source>.+?))?\.?$"
)

# "PlayerX received special loot from a raid: Twisted bow."
_RAID_LOOT_PATTERN = re.compile(
    r"^(?P<player>.+?) received special loot from a raid: (?P<item>.+?)\.?$"
)

# "PlayerX has reached level 85 in Attack."
_LEVEL_PATTERN = re.compile(
    r"^(?P<player>.+?) has reached level (?P<level>\d+) in (?P<skill>.+?)\.?$"
)

# "PlayerX has reached the highest level in Slayer."
_MAX_LEVEL_PATTERN = re.compile(
    r"^(?P<player>.+?) has reached the highest level in (?P<skill>.+?)\.?$"
)

# "PlayerX has completed a quest: Dragon Slayer II"
_QUEST_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed a quest: (?P<name>.+?)\.?$"
)

# "PlayerX has completed the Ardougne Easy diary."
_DIARY_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed the (?P<name>.+? diary)\.?$"
)

# "PlayerX has completed the combat achievement: Ghommal's Hilt 6."
_COMBAT_ACH_PATTERN = re.compile(
    r"^(?P<player>.+?) has completed the combat achievement: (?P<name>.+?)\.?$"
)

# "PlayerX has a funny feeling like they're being followed."
# "PlayerX feels something weird sneaking into their backpack."
_PET_PATTERNS = [
    re.compile(r"^(?P<player>.+?) has a funny feeling like they'?re being followed"),
    re.compile(r"^(?P<player>.+?) feels something weird sneaking into their backpack"),
]

# "PlayerX has been invited into the clan by Inviter."
_NEW_MEMBER_PATTERN = re.compile(
    r"^(?P<player>.+?) has been invited into the clan by (?P<inviter>.+?)\.?$"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(message: str) -> BroadcastType:
    """Return the broadcast type for a clan MESSAGE (not a player chat line)."""
    if _LOOT_PATTERN.match(message) or _RAID_LOOT_PATTERN.match(message):
        return BroadcastType.LOOT
    if _LEVEL_PATTERN.match(message) or _MAX_LEVEL_PATTERN.match(message):
        return BroadcastType.LEVEL_UP
    if _QUEST_PATTERN.match(message):
        return BroadcastType.QUEST
    if _DIARY_PATTERN.match(message):
        return BroadcastType.DIARY
    if _COMBAT_ACH_PATTERN.match(message):
        return BroadcastType.COMBAT_ACHIEVEMENT
    if any(p.match(message) for p in _PET_PATTERNS):
        return BroadcastType.PET
    if _NEW_MEMBER_PATTERN.match(message):
        return BroadcastType.NEW_MEMBER
    return BroadcastType.UNKNOWN


def parse_loot(message: str) -> ParsedLoot | None:
    if m := _LOOT_PATTERN.match(message):
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(m.group("value").replace(",", "")),
            source=m.group("source"),
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
    if m := _LEVEL_PATTERN.match(message):
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(m.group("level")),
        )
    if m := _MAX_LEVEL_PATTERN.match(message):
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=99,
        )
    return None


def parse_achievement(message: str) -> ParsedAchievement | None:
    if m := _QUEST_PATTERN.match(message):
        return ParsedAchievement(player_name=m.group("player"), kind="quest", name=m.group("name"))
    if m := _DIARY_PATTERN.match(message):
        return ParsedAchievement(player_name=m.group("player"), kind="diary", name=m.group("name"))
    if m := _COMBAT_ACH_PATTERN.match(message):
        return ParsedAchievement(player_name=m.group("player"), kind="combat_achievement", name=m.group("name"))
    return None


def parse_pet(message: str) -> ParsedPet | None:
    for pattern in _PET_PATTERNS:
        if m := pattern.match(message):
            return ParsedPet(player_name=m.group("player"))
    return None


def parse_new_member(message: str) -> ParsedNewMember | None:
    if m := _NEW_MEMBER_PATTERN.match(message):
        return ParsedNewMember(player_name=m.group("player"), invited_by=m.group("inviter"))
    return None
