"""Parse OSRS clan broadcast messages into structured event data."""

from __future__ import annotations

from . import patterns
from .types import (
    BroadcastType,
    ParsedAchievement,
    ParsedClanLeave,
    ParsedClueItem,
    ParsedCofferTransaction,
    ParsedCollectionLog,
    ParsedHcimDeath,
    ParsedLeagueArea,
    ParsedLeagueRank,
    ParsedLeagueRelic,
    ParsedLevelUp,
    ParsedLoot,
    ParsedLootKey,
    ParsedNewMember,
    ParsedPersonalBest,
    ParsedPet,
    ParsedPk,
    ParsedXpMilestone,
)


def classify(message: str) -> BroadcastType:
    """Return the broadcast type for a clan broadcast message."""
    message = patterns.strip(message)
    if patterns.LOOT.match(message) or patterns.RAID_LOOT.match(message):
        return BroadcastType.LOOT
    if patterns.LEVEL_IN.match(message) or patterns.LEVEL_OF.match(message):
        return BroadcastType.LEVEL_UP
    if patterns.XP_MILESTONE.match(message):
        return BroadcastType.XP_MILESTONE
    if patterns.QUEST.match(message):
        return BroadcastType.QUEST
    if patterns.DIARY.match(message):
        return BroadcastType.DIARY
    if (
        patterns.COMBAT_ACH.match(message)
        or patterns.COMBAT_TIER.match(message)
        or patterns.COMBAT_TIER_UNLOCK.match(message)
    ):
        return BroadcastType.COMBAT_ACHIEVEMENT
    if any(p.match(message) for p in patterns.PET):
        return BroadcastType.PET
    if patterns.NEW_MEMBER.match(message):
        return BroadcastType.NEW_MEMBER
    if patterns.COLLECTION_LOG.match(message):
        return BroadcastType.COLLECTION_LOG
    if patterns.LOOT_KEY.match(message):
        return BroadcastType.LOOT_KEY
    if patterns.CLUE_ITEM.match(message):
        return BroadcastType.CLUE_ITEM
    if patterns.PK_WINNER.match(message) or patterns.PK_LOSER.match(message):
        return BroadcastType.PK
    if patterns.PERSONAL_BEST.match(message):
        return BroadcastType.PERSONAL_BEST
    if patterns.LEFT_CLAN.match(message):
        return BroadcastType.LEFT_CLAN
    if patterns.EXPELLED.match(message):
        return BroadcastType.EXPELLED
    if m := patterns.COFFER.match(message):
        return (
            BroadcastType.COFFER_DONATION
            if m.group("action") == "deposited"
            else BroadcastType.COFFER_WITHDRAWAL
        )
    if patterns.HCIM_DEATH.match(message):
        return BroadcastType.HCIM_DEATH
    if patterns.LEAGUE_RELIC.match(message):
        return BroadcastType.LEAGUE_RELIC
    if patterns.LEAGUE_RANK.match(message):
        return BroadcastType.LEAGUE_RANK
    if patterns.LEAGUE_AREA.match(message):
        return BroadcastType.LEAGUE_AREA
    return BroadcastType.UNKNOWN


def parse_loot(message: str) -> ParsedLoot | None:
    message = patterns.strip(message)
    if m := patterns.LOOT.match(message):
        raw_value = m.group("value")
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
            source=m.group("source") or "Generic PVM",
        )
    if m := patterns.RAID_LOOT.match(message):
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=None,
            source="raid",
        )
    return None


def parse_level_up(message: str) -> ParsedLevelUp | None:
    message = patterns.strip(message)
    if m := patterns.LEVEL_IN.match(message):
        level_str = m.group("level")
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(level_str) if level_str else 99,
        )
    if m := patterns.LEVEL_OF.match(message):
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(m.group("level")),
        )
    return None


def parse_xp_milestone(message: str) -> ParsedXpMilestone | None:
    message = patterns.strip(message)
    if m := patterns.XP_MILESTONE.match(message):
        return ParsedXpMilestone(
            player_name=m.group("player"),
            skill=m.group("skill"),
            xp=int(m.group("xp").replace(",", "")),
        )
    return None


def parse_achievement(message: str) -> ParsedAchievement | None:
    message = patterns.strip(message)
    if m := patterns.QUEST.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="quest", name=m.group("name")
        )
    if m := patterns.DIARY.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="diary", name=m.group("name")
        )
    if m := patterns.COMBAT_ACH.match(message):
        diff = m.group("difficulty")
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=m.group("name"),
            difficulty=diff.lower() if diff else None,
        )
    if m := patterns.COMBAT_TIER.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    if m := patterns.COMBAT_TIER_UNLOCK.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    return None


def parse_pet(message: str) -> ParsedPet | None:
    message = patterns.strip(message)
    for pattern in patterns.PET:
        if m := pattern.match(message):
            return ParsedPet(player_name=m.group("player"))
    return None


def parse_new_member(message: str) -> ParsedNewMember | None:
    message = patterns.strip(message)
    if m := patterns.NEW_MEMBER.match(message):
        return ParsedNewMember(
            player_name=m.group("player"), invited_by=m.group("inviter")
        )
    return None


def parse_collection_log(message: str) -> ParsedCollectionLog | None:
    message = patterns.strip(message)
    if m := patterns.COLLECTION_LOG.match(message):
        return ParsedCollectionLog(
            player_name=m.group("player"),
            item_name=m.group("item"),
            log_slots=int(m.group("slots")),
            log_slots_max=int(m.group("max")),
        )
    return None


def parse_loot_key(message: str) -> ParsedLootKey | None:
    message = patterns.strip(message)
    if m := patterns.LOOT_KEY.match(message):
        return ParsedLootKey(
            player_name=m.group("player"),
            coin_value=int(m.group("value").replace(",", "")),
        )
    return None


def parse_clue_item(message: str) -> ParsedClueItem | None:
    message = patterns.strip(message)
    if m := patterns.CLUE_ITEM.match(message):
        raw_value = m.group("value")
        return ParsedClueItem(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
        )
    return None


def parse_pk(message: str) -> ParsedPk | None:
    message = patterns.strip(message)
    if m := patterns.PK_WINNER.match(message):
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(m.group("gp").replace(",", "")),
        )
    if m := patterns.PK_LOSER.match(message):
        raw_gp = m.group("gp")
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(raw_gp.replace(",", "")) if raw_gp else None,
        )
    return None


def parse_personal_best(message: str) -> ParsedPersonalBest | None:
    message = patterns.strip(message)
    if m := patterns.PERSONAL_BEST.match(message):
        return ParsedPersonalBest(
            player_name=m.group("player"),
            activity=m.group("activity"),
            time_seconds=patterns.parse_osrs_time(m.group("time")),
            variant=m.group("variant"),
        )
    return None


def parse_clan_leave(message: str) -> ParsedClanLeave | None:
    message = patterns.strip(message)
    if m := patterns.LEFT_CLAN.match(message):
        return ParsedClanLeave(player_name=m.group("player"), expelled_by=None)
    if m := patterns.EXPELLED.match(message):
        return ParsedClanLeave(
            player_name=m.group("player"), expelled_by=m.group("mod")
        )
    return None


def parse_coffer_transaction(message: str) -> ParsedCofferTransaction | None:
    message = patterns.strip(message)
    if m := patterns.COFFER.match(message):
        return ParsedCofferTransaction(
            player_name=m.group("player"),
            amount=int(m.group("gp").replace(",", "")),
            is_donation=m.group("action") == "deposited",
        )
    return None


def parse_hcim_death(message: str) -> ParsedHcimDeath | None:
    message = patterns.strip(message)
    if m := patterns.HCIM_DEATH.match(message):
        return ParsedHcimDeath(player_name=m.group("player"))
    return None


def parse_league_relic(message: str) -> ParsedLeagueRelic | None:
    message = patterns.strip(message)
    if m := patterns.LEAGUE_RELIC.match(message):
        return ParsedLeagueRelic(
            player_name=m.group("player"), tier=int(m.group("tier"))
        )
    return None


def parse_league_rank(message: str) -> ParsedLeagueRank | None:
    message = patterns.strip(message)
    if m := patterns.LEAGUE_RANK.match(message):
        return ParsedLeagueRank(player_name=m.group("player"), rank=m.group("rank"))
    return None


def parse_league_area(message: str) -> ParsedLeagueArea | None:
    message = patterns.strip(message)
    if m := patterns.LEAGUE_AREA.match(message):
        nth = m.group("nth")
        return ParsedLeagueArea(
            player_name=m.group("player"), area_count=int(nth) if nth else None
        )
    return None
