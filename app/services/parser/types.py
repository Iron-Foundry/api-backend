from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


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
    source: str | None


@dataclass
class ParsedLevelUp:
    player_name: str
    skill: str
    new_level: int


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
    difficulty: str | None = None


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
    expelled_by: str | None


@dataclass
class ParsedCofferTransaction:
    player_name: str
    amount: int
    is_donation: bool


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
    area_count: int | None
