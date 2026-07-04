"""Classifier for WOM bulk-gained flat data arrays into skills/bosses/activities."""

from __future__ import annotations

_SKILL_SLUGS: frozenset[str] = frozenset(
    {
        "overall",
        "attack",
        "defence",
        "strength",
        "hitpoints",
        "ranged",
        "prayer",
        "magic",
        "cooking",
        "woodcutting",
        "fletching",
        "fishing",
        "firemaking",
        "crafting",
        "smithing",
        "mining",
        "herblore",
        "agility",
        "thieving",
        "slayer",
        "farming",
        "runecrafting",
        "hunter",
        "construction",
        "sailing",
    }
)

_ACTIVITY_SLUGS: frozenset[str] = frozenset(
    {
        "bounty_hunter_hunter",
        "bounty_hunter_rogue",
        "bounty_hunter_legacy_hunter",
        "bounty_hunter_legacy_rogue",
        "clue_scrolls_all",
        "clue_scrolls_beginner",
        "clue_scrolls_easy",
        "clue_scrolls_medium",
        "clue_scrolls_hard",
        "clue_scrolls_elite",
        "clue_scrolls_master",
        "colosseum_glory",
        "collections_logged",
        "combat_achievement_points",
        "guardians_of_the_rift",
        "last_man_standing",
        "league_points",
        "nightmare_zone",
        "pvp_arena",
        "rifts_closed",
        "soul_wars_zeal",
        "tempoross",
        "wintertodt",
    }
)

_COMPUTED_SLUGS: frozenset[str] = frozenset({"ehp", "ehb"})


def parse_bulk_gains_data(
    data: list[dict],
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Split a WOM bulk-gained data array into (skills, bosses, activities) dicts.

    Each value is {gained, start, end} from the WOM response. Computed metrics
    (ehp, ehb) are discarded.
    """
    skills: dict[str, dict] = {}
    bosses: dict[str, dict] = {}
    activities: dict[str, dict] = {}

    for entry in data:
        metric: str = entry.get("metric", "")
        if not metric or metric in _COMPUTED_SLUGS:
            continue
        record = {
            "gained": entry.get("gained", 0),
            "start": entry.get("start", 0),
            "end": entry.get("end", 0),
        }
        if metric in _SKILL_SLUGS:
            skills[metric] = record
        elif metric in _ACTIVITY_SLUGS:
            activities[metric] = record
        else:
            bosses[metric] = record

    return skills, bosses, activities
