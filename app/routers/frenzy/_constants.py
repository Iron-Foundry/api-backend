from __future__ import annotations

import os

_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")
_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")

_LB_FRESH_KEY = "frenzy:leaderboards:fresh"
_LB_STALE_KEY = "frenzy:leaderboards:stale"
_LB_LOCK_KEY = "frenzy:leaderboards:lock"
_LB_FRESH_TTL = 5 * 60
_LB_STALE_TTL = 2 * 60 * 60
_LB_LOCK_TTL = 120

_ITEMS_KEY = "osrs:items:mapping"
_BOSSES_KEY = "osrs:bosses:list"
_ACTIVITIES_KEY = "osrs:activities:list"
_OSRS_REF_TTL = 24 * 60 * 60

_VALID_SOURCES = {"trackscape", "discord_ocr", "discord_manual", "web"}
_VALID_SUBMISSION_TYPES = {"item", "activity", "milestone"}
_VALID_STATUSES = {"pending", "approved", "rejected"}

_WIKI_IMAGE_BASE = "https://oldschool.runescape.wiki/images"


def _wiki_icon(slug: str) -> str:
    return f"{_WIKI_IMAGE_BASE}/{slug}.png"


_BOSS_METRICS: dict[str, tuple[str, str]] = {
    "abyssal_sire": ("Abyssal Sire", "Abyssal_Sire"),
    "alchemical_hydra": ("Alchemical Hydra", "Alchemical_Hydra"),
    "amoxliatl": ("Amoxliatl", "Amoxliatl"),
    "araxxor": ("Araxxor", "Araxxor"),
    "artio": ("Artio", "Artio"),
    "barrows_chests": ("Barrows Chests", "Barrows"),
    "bryophyta": ("Bryophyta", "Bryophyta"),
    "callisto": ("Callisto", "Callisto"),
    "calvarion": ("Calvar'ion", "Calvar%27ion"),
    "cerberus": ("Cerberus", "Cerberus"),
    "chambers_of_xeric": ("Chambers of Xeric", "Chambers_of_Xeric"),
    "chambers_of_xeric_challenge_mode": ("Chambers of Xeric: CM", "Chambers_of_Xeric"),
    "chaos_elemental": ("Chaos Elemental", "Chaos_Elemental"),
    "chaos_fanatic": ("Chaos Fanatic", "Chaos_Fanatic"),
    "commander_zilyana": ("Commander Zilyana", "Commander_Zilyana"),
    "corporeal_beast": ("Corporeal Beast", "Corporeal_Beast"),
    "crazy_archaeologist": ("Crazy Archaeologist", "Crazy_Archaeologist"),
    "dagannoth_prime": ("Dagannoth Prime", "Dagannoth_Prime"),
    "dagannoth_rex": ("Dagannoth Rex", "Dagannoth_Rex"),
    "dagannoth_supreme": ("Dagannoth Supreme", "Dagannoth_Supreme"),
    "deranged_archaeologist": ("Deranged Archaeologist", "Deranged_Archaeologist"),
    "duke_sucellus": ("Duke Sucellus", "Duke_Sucellus"),
    "general_graardor": ("General Graardor", "General_Graardor"),
    "giant_mole": ("Giant Mole", "Giant_Mole"),
    "grotesque_guardians": ("Grotesque Guardians", "Grotesque_Guardians"),
    "hespori": ("Hespori", "Hespori"),
    "kalphite_queen": ("Kalphite Queen", "Kalphite_Queen"),
    "king_black_dragon": ("King Black Dragon", "King_Black_Dragon"),
    "kraken": ("Kraken", "Kraken"),
    "kree_arra": ("Kree'arra", "Kree%27arra"),
    "kril_tsutsaroth": ("K'ril Tsutsaroth", "K%27ril_Tsutsaroth"),
    "lunar_chests": ("Lunar Chests", "Lunar_Chests"),
    "mimic": ("Mimic", "Mimic_(monster)"),
    "nex": ("Nex", "Nex"),
    "nightmare": ("Nightmare", "The_Nightmare"),
    "obor": ("Obor", "Obor"),
    "phantom_muspah": ("Phantom Muspah", "Phantom_Muspah"),
    "phosanis_nightmare": ("Phosani's Nightmare", "Phosani%27s_Nightmare"),
    "royal_titans": ("Royal Titans", "Royal_Titans"),
    "sarachnis": ("Sarachnis", "Sarachnis"),
    "scorpia": ("Scorpia", "Scorpia"),
    "scurrius": ("Scurrius", "Scurrius"),
    "skotizo": ("Skotizo", "Skotizo"),
    "sol_heredit": ("Sol Heredit", "Sol_Heredit"),
    "spindel": ("Spindel", "Spindel"),
    "tempoross": ("Tempoross", "Tempoross"),
    "the_corrupted_gauntlet": ("The Corrupted Gauntlet", "The_Corrupted_Gauntlet"),
    "the_gauntlet": ("The Gauntlet", "The_Gauntlet"),
    "the_hueycoatl": ("The Hueycoatl", "The_Hueycoatl"),
    "the_leviathan": ("The Leviathan", "The_Leviathan"),
    "the_whisperer": ("The Whisperer", "The_Whisperer"),
    "theatre_of_blood": ("Theatre of Blood", "Theatre_of_Blood"),
    "theatre_of_blood_hard_mode": ("Theatre of Blood: HM", "Theatre_of_Blood"),
    "thermonuclear_smoke_devil": ("Thermonuclear Smoke Devil", "Thermonuclear_Smoke_Devil"),
    "tombs_of_amascut": ("Tombs of Amascut", "Tombs_of_Amascut"),
    "tombs_of_amascut_expert_mode": ("Tombs of Amascut: Expert", "Tombs_of_Amascut"),
    "tzkal_zuk": ("TzKal-Zuk", "TzKal-Zuk"),
    "tztok_jad": ("TzTok-Jad", "TzTok-Jad"),
    "vardorvis": ("Vardorvis", "Vardorvis"),
    "venenatis": ("Venenatis", "Venenatis"),
    "vetion": ("Vet'ion", "Vet%27ion"),
    "vorkath": ("Vorkath", "Vorkath"),
    "wintertodt": ("Wintertodt", "Wintertodt"),
    "yama": ("Yama", "Yama"),
    "zalcano": ("Zalcano", "Zalcano"),
    "zulrah": ("Zulrah", "Zulrah"),
}

_ACTIVITY_METRICS: dict[str, tuple[str, str]] = {
    "bounty_hunter_hunter": ("Bounty Hunter - Hunter", "Bounty_Hunter"),
    "bounty_hunter_rogue": ("Bounty Hunter - Rogue", "Bounty_Hunter"),
    "clue_scrolls_all": ("Clue Scrolls (All)", "Clue_scroll"),
    "clue_scrolls_beginner": ("Clue Scrolls (Beginner)", "Clue_scroll_(beginner)"),
    "clue_scrolls_easy": ("Clue Scrolls (Easy)", "Clue_scroll_(easy)"),
    "clue_scrolls_medium": ("Clue Scrolls (Medium)", "Clue_scroll_(medium)"),
    "clue_scrolls_hard": ("Clue Scrolls (Hard)", "Clue_scroll_(hard)"),
    "clue_scrolls_elite": ("Clue Scrolls (Elite)", "Clue_scroll_(elite)"),
    "clue_scrolls_master": ("Clue Scrolls (Master)", "Clue_scroll_(master)"),
    "colosseum_glory": ("Colosseum Glory", "Fortis_Colosseum"),
    "collections_logged": ("Collections Logged", "Collection_log"),
    "combat_achievement_points": ("Combat Achievement Points", "Combat_Achievements"),
    "gotr_runes_crafted": ("GOTR Runes Crafted", "Guardians_of_the_Rift"),
    "guardians_of_the_rift": ("Guardians of the Rift", "Guardians_of_the_Rift"),
    "last_man_standing": ("Last Man Standing", "Last_Man_Standing"),
    "league_points": ("League Points", "Trailblazer_Reloaded_League"),
    "nightmare_zone": ("Nightmare Zone", "Nightmare_Zone"),
    "pvp_arena_rank": ("PvP Arena", "PvP_Arena"),
    "rifts_closed": ("Rifts Closed", "Guardians_of_the_Rift"),
    "soul_wars_zeal": ("Soul Wars Zeal", "Soul_Wars"),
    "tempoross": ("Tempoross", "Tempoross"),
    "theatre_of_blood_hard_mode": ("ToB: Hard Mode", "Theatre_of_Blood"),
    "wintertodt": ("Wintertodt", "Wintertodt"),
}
