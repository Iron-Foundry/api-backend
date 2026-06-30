from __future__ import annotations

import os

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_API_KEY = os.getenv("WOM_API_KEY")
_WOM_GROUP_KEY = os.getenv("WOM_GROUP_KEY")
_WOM_DISCORD_CONTACT = os.getenv("WOM_DISCORD_CONTACT")

_GLOBAL_GUILD_ID = 0
_COMP_METRIC_MAP_KEY = "competition_metric_map"

_DROP_MIN_VALUE = 2_000_000
_XP_MIN_MILESTONE = 15_000_000
_XP_STEP = 5_000_000

_RAID_METRICS = [
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert_mode",
]

_KC_METRICS: dict[str, str] = {
    "abyssal_sire": "Abyssal Sire",
    "alchemical_hydra": "Alchemical Hydra",
    "amoxliatl": "Amoxliatl",
    "araxxor": "Araxxor",
    "artio": "Artio",
    "barrows_chests": "Barrows",
    "bryophyta": "Bryophyta",
    "callisto": "Callisto",
    "calvarion": "Calvar'ion",
    "cerberus": "Cerberus",
    "chambers_of_xeric": "Chambers of Xeric",
    "chambers_of_xeric_challenge_mode": "CoX: Challenge Mode",
    "chaos_elemental": "Chaos Elemental",
    "chaos_fanatic": "Chaos Fanatic",
    "commander_zilyana": "Commander Zilyana",
    "corporeal_beast": "Corporeal Beast",
    "crazy_archaeologist": "Crazy Archaeologist",
    "dagannoth_prime": "Dagannoth Prime",
    "dagannoth_rex": "Dagannoth Rex",
    "dagannoth_supreme": "Dagannoth Supreme",
    "deranged_archaeologist": "Deranged Archaeologist",
    "duke_sucellus": "Duke Sucellus",
    "general_graardor": "General Graardor",
    "giant_mole": "Giant Mole",
    "grotesque_guardians": "Grotesque Guardians",
    "hespori": "Hespori",
    "kalphite_queen": "Kalphite Queen",
    "king_black_dragon": "King Black Dragon",
    "kraken": "Kraken",
    "kree_arra": "Kree'arra",
    "kril_tsutsaroth": "K'ril Tsutsaroth",
    "lunar_chests": "Lunar Chests",
    "maggot_king": "Maggot King",
    "mimic": "Mimic",
    "nex": "Nex",
    "nightmare": "Nightmare",
    "obor": "Obor",
    "phantom_muspah": "Phantom Muspah",
    "phosanis_nightmare": "Phosani's Nightmare",
    "scurrius": "Scurrius",
    "skotizo": "Skotizo",
    "sol_heredit": "Sol Heredit",
    "spindel": "Spindel",
    "tempoross": "Tempoross",
    "the_corrupted_gauntlet": "The Corrupted Gauntlet",
    "the_gauntlet": "The Gauntlet",
    "the_hueycoatl": "The Hueycoatl",
    "the_leviathan": "The Leviathan",
    "the_whisperer": "The Whisperer",
    "theatre_of_blood": "Theatre of Blood",
    "theatre_of_blood_hard_mode": "ToB: Hard Mode",
    "thermonuclear_smoke_devil": "Thermonuclear Smoke Devil",
    "tombs_of_amascut": "Tombs of Amascut",
    "tombs_of_amascut_expert_mode": "ToA: Expert Mode",
    "tzkal_zuk": "TzKal-Zuk",
    "tztok_jad": "TzTok-Jad",
    "vardorvis": "Vardorvis",
    "venenatis": "Venenatis",
    "vetion": "Vet'ion",
    "vorkath": "Vorkath",
    "wintertodt": "Wintertodt",
    "zalcano": "Zalcano",
    "zulrah": "Zulrah",
}

_KC_FRESH_KEY = "clan:kc_fresh"
_KC_STALE_KEY = "clan:kc_stale"
_KC_LOCK_KEY = "clan:kc_lock"
_KC_FRESH_TTL = 15 * 60
_KC_STALE_TTL = 48 * 60 * 60
_KC_LOCK_TTL = 300

_LEAGUES_FRESH_KEY = "clan:leagues_fresh"
_LEAGUES_STALE_KEY = "clan:leagues_stale"
_LEAGUES_LOCK_KEY = "clan:leagues_lock"
_LEAGUES_FRESH_TTL = 15 * 60
_LEAGUES_STALE_TTL = 48 * 60 * 60
_LEAGUES_LOCK_TTL = 60

_NC_FRESH_KEY = "clan:name_changes_fresh"
_NC_STALE_KEY = "clan:name_changes_stale"
_NC_LOCK_KEY = "clan:name_changes_lock"
_NC_FRESH_TTL = 15 * 60
_NC_STALE_TTL = 6 * 60 * 60
_NC_LOCK_TTL = 60

_COMPS_FRESH_KEY = "clan:competitions_fresh"
_COMPS_STALE_KEY = "clan:competitions_stale"
_COMPS_LOCK_KEY = "clan:competitions_lock"
_COMPS_FRESH_TTL = 5 * 60
_COMPS_STALE_TTL = 2 * 60 * 60
_COMPS_LOCK_TTL = 120

_COMP_METRIC_ONGOING_FRESH_TTL = 5 * 60
_COMP_METRIC_UPCOMING_FRESH_TTL = 15 * 60
_COMP_METRIC_FINISHED_FRESH_TTL = 60 * 60
_COMP_METRIC_STALE_TTL = 2 * 60 * 60
_COMP_METRIC_LOCK_TTL = 60
