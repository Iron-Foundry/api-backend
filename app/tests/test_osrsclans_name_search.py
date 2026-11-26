"""Fuzzy OSRS name matching: case, accents and punctuation do not count."""

from __future__ import annotations

import pytest

from app.services.osrsclans.name_search import best_matches, name_entries, search_key


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("K'ril Tsutsaroth", "kril tsutsaroth"),
        (f"Vet{chr(0x2019)}ion", "vetion"),
        ("Dragon-hunter_crossbow", "dragon hunter crossbow"),
        (f"Pok{chr(0xE9)}mon{chr(0xB4)}s  cape", "pokemons cape"),
        ("Kodai (+)(2)", "kodai 2"),
    ],
)
def test_search_key_drops_case_accents_and_marks(text: str, key: str) -> None:
    assert search_key(text) == key


_NAMES = [
    (9, "Cave kraken"),
    (8, "Kraken boss"),
    (7, "Kraken"),
    (6, "Kodai wand"),
    (5, "Kodai wand"),
    (4, "Kraken tentacle"),
]


@pytest.mark.parametrize(
    ("q", "unique", "expected"),
    [
        ("kraken", False, [7, 8, 4, 9]),
        ("KODAI-wand", False, [5, 6]),
        ("kodai wand", True, [5]),
        ("kra ken", False, [7, 8, 4, 9]),
        ("--", False, []),
    ],
)
def test_best_matches_rank_exact_prefix_word_then_any(
    q: str, unique: bool, expected: list[int]
) -> None:
    hits = best_matches(name_entries(_NAMES), q, unique_names=unique)
    assert [e.id for e in hits] == expected
