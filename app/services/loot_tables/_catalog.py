"""Builds the loot-source catalog from the boss metric list plus TOML overrides."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.services.ranking_service._boss_defaults import DEFAULT_BOSS_METRICS

_DATA_FILE = Path(__file__).parent / "data" / "sources.toml"
_LOWER_WORDS = {"of", "the", "and", "in"}


@dataclass(frozen=True)
class LootSourceEntry:
    slug: str
    display_name: str
    category: str
    wiki_page: str
    reward_kind: str | None = None


def _humanize(slug: str) -> str:
    words = slug.split("_")
    parts = [
        word if word in _LOWER_WORDS and index > 0 else word.capitalize()
        for index, word in enumerate(words)
    ]
    return " ".join(parts)


def load_catalog() -> list[LootSourceEntry]:
    config = tomllib.loads(_DATA_FILE.read_text(encoding="utf-8"))
    overrides: dict[str, str] = config.get("overrides", {})
    excluded: set[str] = set(config.get("loot_exclude", []))
    chest: set[str] = set(config.get("chest_sources", []))
    entries: list[LootSourceEntry] = []

    def _reward_kind(slug: str) -> str | None:
        return "chest" if slug in chest else None

    for boss in DEFAULT_BOSS_METRICS:
        slug = boss.name
        if slug in excluded:
            continue
        wiki_page = overrides.get(slug, _humanize(slug))
        entries.append(
            LootSourceEntry(
                slug, _humanize(slug), "boss", wiki_page, _reward_kind(slug)
            )
        )

    for extra in config.get("extra", []):
        slug = extra["slug"]
        if slug in excluded:
            continue
        entries.append(
            LootSourceEntry(
                slug,
                extra["display_name"],
                extra["category"],
                extra["wiki_page"],
                _reward_kind(slug),
            )
        )

    return entries
