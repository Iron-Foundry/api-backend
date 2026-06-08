"""Compiled regexes and string-cleaning helpers for OSRS broadcast parsing."""

from __future__ import annotations

import re

_IMG_TAG_RE = re.compile(r"<img=\d+>\s*")
_CA_ID_RE = re.compile(r"CA_ID:\d+\|")


def strip(message: str) -> str:
    """Remove OSRS image tags and CA_ID prefixes; normalize non-breaking spaces."""
    message = _IMG_TAG_RE.sub("", message).strip()
    message = _CA_ID_RE.sub("", message).strip()
    # OSRS broadcasts use non-breaking spaces (U+00A0) in player names;
    # normalize to regular spaces so player_name comparisons work.
    return message.replace("\xa0", " ")


def parse_osrs_time(time_str: str) -> float:
    """Convert ``MM:SS`` or ``H:MM:SS`` (optional ``.ss``) to total seconds."""
    sub_parts = time_str.split(".")
    sub_seconds = float(f"0.{sub_parts[1]}") if len(sub_parts) > 1 else 0.0
    parts = sub_parts[0].split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1]) + sub_seconds
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + sub_seconds
    return 0.0


LOOT = re.compile(
    r"^(?P<player>.+?) received a drop: (?:(?P<quantity>[\d,]+) x )?(?P<item>.+?)"
    r"(?: \((?P<value>[\d,]+) coins\))?(?: from (?P<source>.+?))?\.?$"
)
RAID_LOOT = re.compile(
    r"^(?P<player>.+?) received special loot from a raid: (?P<item>.+?)\.?$"
)
LEVEL_IN = re.compile(
    r"^(?P<player>.+?) has reached (?:level (?P<level>\d+)|the highest(?: possible)? level) in (?P<skill>.+?)\.?$"
)
LEVEL_OF = re.compile(
    r"^(?P<player>.+?) has reached (?:a )?(?:the highest possible )?(?P<skill>.+?) level(?: of)? (?P<level>\d+)[!.]"
)
XP_MILESTONE = re.compile(
    r"^(?P<player>.+?) has reached (?P<xp>[\d,]+) XP in (?P<skill>.+?)[!.]?$"
)
QUEST = re.compile(r"^(?P<player>.+?) has completed a quest: (?P<name>.+?)\.?$")
DIARY = re.compile(r"^(?P<player>.+?) has completed the (?P<name>.+? diary)\.?$")
COMBAT_ACH = re.compile(
    r"^(?P<player>.+?) has completed "
    r"(?:the combat achievement"
    r"|an? (?P<difficulty>easy|medium|hard|elite|master|grandmaster) combat task)"
    r": (?P<name>.+?)\.?$",
    re.IGNORECASE,
)
COMBAT_TIER = re.compile(
    r"^(?P<player>.+?) has completed all "
    r"(?P<difficulty>easy|medium|hard|elite|master|grandmaster) combat tasks\.?$",
    re.IGNORECASE,
)
COMBAT_TIER_UNLOCK = re.compile(
    r"^(?P<player>.+?) has unlocked the "
    r"(?P<difficulty>easy|medium|hard|elite|master|grandmaster) tier of rewards from Combat Achievements[!.]?$",
    re.IGNORECASE,
)
PET = [
    re.compile(r"^(?P<player>.+?) has a funny feeling like (?:they'?re|he's|she's) being followed"),
    re.compile(r"^(?P<player>.+?) feels something weird sneaking into (?:their|his|her) backpack"),
]
NEW_MEMBER = re.compile(
    r"^(?P<player>.+?) has been invited into the clan by (?P<inviter>.+?)\.?$"
)
COLLECTION_LOG = re.compile(
    r"^(?P<player>.+?) received a new collection log item: (?P<item>.+?) \((?P<slots>\d+)/(?P<max>\d+)\)"
)
LOOT_KEY = re.compile(
    r"^(?P<player>.+?) has opened a loot key worth (?P<value>[\d,]+) coins[!.]"
)
CLUE_ITEM = re.compile(
    r"^(?P<player>.+?) received a clue item: (?P<item>.+?)(?: \((?P<value>[\d,]+) coins\))?\.?$"
)
PK_WINNER = re.compile(
    r"^(?P<winner>.+?) has defeated (?P<loser>.+?) and received \((?P<gp>[\d,]+) coins\) worth of loot[!.]"
)
PK_LOSER = re.compile(
    r"^(?P<loser>.+?) has been defeated by (?P<winner>.+?)"
    r"(?:(?: in .+?)?(?: and lost \((?P<gp>[\d,]+) coins\) worth of loot)?)[!.]"
)
PERSONAL_BEST = re.compile(
    r"^(?P<player>.+?) (?:has )?achieved a new (?P<activity>.+?) "
    r"(?:(?P<variant>Overall|Challenge) )?personal best: (?P<time>[\d:]+(?:\.\d{2})?)$"
)
LEFT_CLAN = re.compile(r"^(?P<player>.+?) has left the clan\.$")
EXPELLED = re.compile(r"^(?P<mod>.+?) has expelled (?P<player>.+?) from the clan\.$")
COFFER = re.compile(
    r"^(?P<player>.+?) has (?P<action>deposited|withdrawn) (?P<gp>[\d,]+) coins (?:into|from) the coffer\."
)
HCIM_DEATH = re.compile(
    r"^(?P<player>.+?) has died and lost their Hardcore Ironman status\.$"
)
LEAGUE_RELIC = re.compile(
    r"^(?P<player>.+?) has unlocked their tier (?P<tier>\d+) League relic!$"
)
LEAGUE_RANK = re.compile(r"^(?P<player>.+?) has earned the (?P<rank>.+?) rank!$")
LEAGUE_AREA = re.compile(
    r"^(?P<player>.+?) has unlocked their (?:(?P<nth>\d+)(?:st|nd|rd|th)|final) League area!$"
)
