"""Fuzzy name matching for OSRS names: case, accents and punctuation do not count.

"kril" finds "K'ril Tsutsaroth", "vetion" finds "Vet'ion", and "dragon-hunter"
finds "Dragon hunter crossbow". A name ranks by how well it matches: the exact
name, then a name that starts with the search, then a name with a word that
starts with it, then any name that holds it. Shorter names come first within a
rank.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_NOT_WORD = re.compile(r"[^0-9a-z]+")
_APOSTROPHES = str.maketrans("", "", "'`" + "".join(map(chr, (0xB4, 0x2018, 0x2019))))


def search_key(text: str) -> str:
    """Return the words of `text` without case, accents or punctuation, one space apart.

    Apostrophes join their word ("K'ril" is "kril"); hyphens, underscores and
    other marks split words.
    """
    joined = text.translate(_APOSTROPHES)
    plain = unicodedata.normalize("NFKD", joined).encode("ascii", "ignore").decode()
    return " ".join(_NOT_WORD.sub(" ", plain.casefold()).split())


@dataclass(frozen=True)
class NameEntry:
    """One named thing with its precomputed match keys."""

    id: int
    name: str
    compact: str
    words: tuple[str, ...]


def name_entries(pairs: Iterable[tuple[int, str]]) -> list[NameEntry]:
    """Return one entry per (id, name) pair with a name, ready to match."""
    entries = []
    for entry_id, name in pairs:
        key = search_key(name)
        if key:
            entries.append(
                NameEntry(entry_id, name, key.replace(" ", ""), tuple(key.split()))
            )
    return entries


def _rank(entry: NameEntry, compact: str, first_word: str) -> int:
    if entry.compact == compact:
        return 0
    if entry.compact.startswith(compact):
        return 1
    return 2 if any(w.startswith(first_word) for w in entry.words) else 3


def best_matches(
    entries: list[NameEntry],
    q: str,
    limit: int | None = None,
    unique_names: bool = False,
) -> list[NameEntry]:
    """Return the entries that hold `q`, best first; with `unique_names`, one per name.

    `limit` None returns all matches.
    """
    key = search_key(q)
    compact = key.replace(" ", "")
    if not compact:
        return []
    first_word = key.split()[0]
    hits = sorted(
        (e for e in entries if compact in e.compact),
        key=lambda e: (_rank(e, compact, first_word), len(e.name), e.name, e.id),
    )
    return _first_per_name(hits, limit) if unique_names else hits[:limit]


def _first_per_name(hits: list[NameEntry], limit: int | None) -> list[NameEntry]:
    kept: list[NameEntry] = []
    seen: set[str] = set()
    for entry in hits:
        if entry.compact not in seen:
            seen.add(entry.compact)
            kept.append(entry)
            if len(kept) == limit:
                break
    return kept
