from __future__ import annotations

from .metrics.boss import BossMetric, BossMetricBuilder


def _b(name: str, tw: float, fkb: float, pkc: float = 5.0) -> BossMetric:
    return (
        BossMetricBuilder(name)
        .points_per_kc(pkc)
        .first_kill_bonus(fkb)
        .tier_weight(tw)
        .build()
    )


DEFAULT_BOSS_METRICS: tuple[BossMetric, ...] = (
    _b("barrows_chests", 1.0, 100.0),
    _b("scurrius", 1.0, 100.0),
    _b("giant_mole", 1.0, 100.0),
    _b("deranged_archaeologist", 1.0, 100.0),
    _b("chaos_fanatic", 1.0, 100.0),
    _b("crazy_archaeologist", 1.0, 100.0),
    _b("obor", 1.0, 100.0),
    _b("bryophyta", 1.0, 100.0),
    _b("amoxliatl", 1.0, 100.0),
    _b("hespori", 1.0, 100.0),
    _b("kraken", 1.0, 100.0),
    _b("shellbane_gryphon", 1.0, 100.0),
    _b("thermonuclear_smoke_devil", 1.0, 100.0),
    _b("dagannoth_prime", 2.0, 200.0),
    _b("dagannoth_rex", 2.0, 200.0),
    _b("dagannoth_supreme", 2.0, 200.0),
    _b("scorpia", 2.0, 200.0),
    _b("king_black_dragon", 2.0, 200.0),
    _b("grotesque_guardians", 2.0, 200.0),
    _b("calvarion", 2.0, 200.0),
    _b("sarachnis", 2.0, 200.0),
    _b("the_hueycoatl", 2.0, 200.0),
    _b("lunar_chests", 2.0, 200.0),
    _b("chaos_elemental", 2.0, 200.0),
    _b("mimic", 2.0, 200.0),
    _b("vetion", 2.0, 200.0),
    _b("spindel", 2.0, 200.0),
    _b("venenatis", 2.0, 200.0),
    _b("artio", 2.0, 200.0),
    _b("callisto", 2.0, 200.0),
    _b("the_royal_titans", 2.0, 200.0),
    _b("skotizo", 2.0, 200.0),
    _b("abyssal_sire", 2.0, 200.0),
    _b("cerberus", 2.0, 200.0),
    _b("alchemical_hydra", 2.0, 200.0),
    _b("kril_tsutsaroth", 2.0, 200.0),
    _b("duke_sucellus", 2.0, 200.0),
    _b("tztok_jad", 2.0, 200.0),
    _b("general_graardor", 3.0, 300.0),
    _b("kreearra", 3.0, 300.0),
    _b("kalphite_queen", 3.0, 300.0),
    _b("commander_zilyana", 3.0, 300.0),
    _b("corporeal_beast", 3.0, 300.0),
    _b("zulrah", 3.0, 300.0),
    _b("vorkath", 3.0, 300.0),
    _b("phantom_muspah", 3.0, 300.0),
    _b("araxxor", 3.0, 300.0),
    _b("the_gauntlet", 3.0, 300.0),
    _b("nex", 4.0, 400.0),
    _b("yama", 4.0, 400.0),
    _b("nightmare", 4.0, 400.0),
    _b("maggot_king", 4.0, 400.0),
    _b("the_leviathan", 4.0, 400.0),
    _b("the_whisperer", 4.0, 400.0),
    _b("vardorvis", 4.0, 400.0),
    _b("the_corrupted_gauntlet", 4.0, 400.0),
    _b("tzkal_zuk", 5.0, 500.0),
    _b("sol_heredit", 5.0, 500.0),
    _b("phosanis_nightmare", 5.0, 500.0),
    _b("doom_of_mokhaiotl", 5.0, 500.0),
    _b("tombs_of_amascut", 3.0, 300.0),
    _b("tombs_of_amascut_expert", 3.0, 400.0),
    _b("theatre_of_blood", 5.0, 500.0),
    _b("theatre_of_blood_hard_mode", 5.0, 600.0),
    _b("chambers_of_xeric", 4.0, 400.0),
    _b("chambers_of_xeric_challenge_mode", 4.0, 500.0),
)
