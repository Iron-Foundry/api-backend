"""Parse OSRS clan broadcast messages into structured event data."""

from __future__ import annotations

from . import patterns as P
from .types import (
    BroadcastType,
    ParsedAchievement,
    ParsedClanLeave,
    ParsedClueItem,
    ParsedCollectionLog,
    ParsedCofferTransaction,
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
    message = P.strip(message)
    if P.LOOT.match(message) or P.RAID_LOOT.match(message):
        return BroadcastType.LOOT
    if P.LEVEL_IN.match(message) or P.LEVEL_OF.match(message):
        return BroadcastType.LEVEL_UP
    if P.XP_MILESTONE.match(message):
        return BroadcastType.XP_MILESTONE
    if P.QUEST.match(message):
        return BroadcastType.QUEST
    if P.DIARY.match(message):
        return BroadcastType.DIARY
    if (
        P.COMBAT_ACH.match(message)
        or P.COMBAT_TIER.match(message)
        or P.COMBAT_TIER_UNLOCK.match(message)
    ):
        return BroadcastType.COMBAT_ACHIEVEMENT
    if any(p.match(message) for p in P.PET):
        return BroadcastType.PET
    if P.NEW_MEMBER.match(message):
        return BroadcastType.NEW_MEMBER
    if P.COLLECTION_LOG.match(message):
        return BroadcastType.COLLECTION_LOG
    if P.LOOT_KEY.match(message):
        return BroadcastType.LOOT_KEY
    if P.CLUE_ITEM.match(message):
        return BroadcastType.CLUE_ITEM
    if P.PK_WINNER.match(message) or P.PK_LOSER.match(message):
        return BroadcastType.PK
    if P.PERSONAL_BEST.match(message):
        return BroadcastType.PERSONAL_BEST
    if P.LEFT_CLAN.match(message):
        return BroadcastType.LEFT_CLAN
    if P.EXPELLED.match(message):
        return BroadcastType.EXPELLED
    if m := P.COFFER.match(message):
        return (
            BroadcastType.COFFER_DONATION
            if m.group("action") == "deposited"
            else BroadcastType.COFFER_WITHDRAWAL
        )
    if P.HCIM_DEATH.match(message):
        return BroadcastType.HCIM_DEATH
    if P.LEAGUE_RELIC.match(message):
        return BroadcastType.LEAGUE_RELIC
    if P.LEAGUE_RANK.match(message):
        return BroadcastType.LEAGUE_RANK
    if P.LEAGUE_AREA.match(message):
        return BroadcastType.LEAGUE_AREA
    return BroadcastType.UNKNOWN


def parse_loot(message: str) -> ParsedLoot | None:
    message = P.strip(message)
    if m := P.LOOT.match(message):
        raw_value = m.group("value")
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
            source=m.group("source") or "Generic PVM",
        )
    if m := P.RAID_LOOT.match(message):
        return ParsedLoot(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=None,
            source="raid",
        )
    return None


def parse_level_up(message: str) -> ParsedLevelUp | None:
    message = P.strip(message)
    if m := P.LEVEL_IN.match(message):
        level_str = m.group("level")
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(level_str) if level_str else 99,
        )
    if m := P.LEVEL_OF.match(message):
        return ParsedLevelUp(
            player_name=m.group("player"),
            skill=m.group("skill"),
            new_level=int(m.group("level")),
        )
    return None


def parse_xp_milestone(message: str) -> ParsedXpMilestone | None:
    message = P.strip(message)
    if m := P.XP_MILESTONE.match(message):
        return ParsedXpMilestone(
            player_name=m.group("player"),
            skill=m.group("skill"),
            xp=int(m.group("xp").replace(",", "")),
        )
    return None


def parse_achievement(message: str) -> ParsedAchievement | None:
    message = P.strip(message)
    if m := P.QUEST.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="quest", name=m.group("name")
        )
    if m := P.DIARY.match(message):
        return ParsedAchievement(
            player_name=m.group("player"), kind="diary", name=m.group("name")
        )
    if m := P.COMBAT_ACH.match(message):
        diff = m.group("difficulty")
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=m.group("name"),
            difficulty=diff.lower() if diff else None,
        )
    if m := P.COMBAT_TIER.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    if m := P.COMBAT_TIER_UNLOCK.match(message):
        diff = m.group("difficulty").lower()
        return ParsedAchievement(
            player_name=m.group("player"),
            kind="combat_achievement",
            name=f"{diff} tier",
            difficulty=diff,
        )
    return None


def parse_pet(message: str) -> ParsedPet | None:
    message = P.strip(message)
    for pattern in P.PET:
        if m := pattern.match(message):
            return ParsedPet(player_name=m.group("player"))
    return None


def parse_new_member(message: str) -> ParsedNewMember | None:
    message = P.strip(message)
    if m := P.NEW_MEMBER.match(message):
        return ParsedNewMember(
            player_name=m.group("player"), invited_by=m.group("inviter")
        )
    return None


def parse_collection_log(message: str) -> ParsedCollectionLog | None:
    message = P.strip(message)
    if m := P.COLLECTION_LOG.match(message):
        return ParsedCollectionLog(
            player_name=m.group("player"),
            item_name=m.group("item"),
            log_slots=int(m.group("slots")),
            log_slots_max=int(m.group("max")),
        )
    return None


def parse_loot_key(message: str) -> ParsedLootKey | None:
    message = P.strip(message)
    if m := P.LOOT_KEY.match(message):
        return ParsedLootKey(
            player_name=m.group("player"),
            coin_value=int(m.group("value").replace(",", "")),
        )
    return None


def parse_clue_item(message: str) -> ParsedClueItem | None:
    message = P.strip(message)
    if m := P.CLUE_ITEM.match(message):
        raw_value = m.group("value")
        return ParsedClueItem(
            player_name=m.group("player"),
            item_name=m.group("item"),
            coin_value=int(raw_value.replace(",", "")) if raw_value else None,
        )
    return None


def parse_pk(message: str) -> ParsedPk | None:
    message = P.strip(message)
    if m := P.PK_WINNER.match(message):
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(m.group("gp").replace(",", "")),
        )
    if m := P.PK_LOSER.match(message):
        raw_gp = m.group("gp")
        return ParsedPk(
            winner=m.group("winner"),
            loser=m.group("loser"),
            gp_exchanged=int(raw_gp.replace(",", "")) if raw_gp else None,
        )
    return None


def parse_personal_best(message: str) -> ParsedPersonalBest | None:
    message = P.strip(message)
    if m := P.PERSONAL_BEST.match(message):
        return ParsedPersonalBest(
            player_name=m.group("player"),
            activity=m.group("activity"),
            time_seconds=P.parse_osrs_time(m.group("time")),
            variant=m.group("variant"),
        )
    return None


def parse_clan_leave(message: str) -> ParsedClanLeave | None:
    message = P.strip(message)
    if m := P.LEFT_CLAN.match(message):
        return ParsedClanLeave(player_name=m.group("player"), expelled_by=None)
    if m := P.EXPELLED.match(message):
        return ParsedClanLeave(
            player_name=m.group("player"), expelled_by=m.group("mod")
        )
    return None


def parse_coffer_transaction(message: str) -> ParsedCofferTransaction | None:
    message = P.strip(message)
    if m := P.COFFER.match(message):
        return ParsedCofferTransaction(
            player_name=m.group("player"),
            amount=int(m.group("gp").replace(",", "")),
            is_donation=m.group("action") == "deposited",
        )
    return None


def parse_hcim_death(message: str) -> ParsedHcimDeath | None:
    message = P.strip(message)
    if m := P.HCIM_DEATH.match(message):
        return ParsedHcimDeath(player_name=m.group("player"))
    return None


def parse_league_relic(message: str) -> ParsedLeagueRelic | None:
    message = P.strip(message)
    if m := P.LEAGUE_RELIC.match(message):
        return ParsedLeagueRelic(
            player_name=m.group("player"), tier=int(m.group("tier"))
        )
    return None


def parse_league_rank(message: str) -> ParsedLeagueRank | None:
    message = P.strip(message)
    if m := P.LEAGUE_RANK.match(message):
        return ParsedLeagueRank(player_name=m.group("player"), rank=m.group("rank"))
    return None


def parse_league_area(message: str) -> ParsedLeagueArea | None:
    message = P.strip(message)
    if m := P.LEAGUE_AREA.match(message):
        nth = m.group("nth")
        return ParsedLeagueArea(
            player_name=m.group("player"), area_count=int(nth) if nth else None
        )
    return None
