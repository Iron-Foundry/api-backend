"""Parse a monster page's wikitext into structured drop rows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._expr import rarity_from_expr
from ._wikitext import parse_named_fields, split_template_fields, strip_comments

_H2_RE = re.compile(r"^==\s*([^=].*?)\s*==\s*$")
_HSUB_RE = re.compile(r"^={3,}\s*(.*?)\s*={3,}\s*$")
_DROPSLINE_RE = re.compile(r"\{\{\s*[A-Za-z]*DropsLine[A-Za-z]*\s*\|", re.IGNORECASE)
_RARITY_RE = re.compile(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)")
_FRACTION_RE = re.compile(
    r"\{\{\s*[Ff]rac(?:tion)?\s*\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)", re.IGNORECASE
)
_MARKUP_RE = re.compile(r"<[^>]+>|\{\{.*?\}\}|\[\[|\]\]")
_SECTION_KEYWORDS = ("drop", "loot", "reward")
_BLANK_RARITY = {"varies"}


@dataclass
class ParsedDrop:
    item_name: str
    quantity_low: int
    quantity_high: int
    noted: bool
    rarity_num: int | None
    rarity_denom: int | None
    rarity_text: str | None
    rolls: int
    drop_group: str


def _to_int(value: str) -> int:
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else 0


def _is_drop_section(title: str) -> bool:
    low = title.lower()
    return any(keyword in low for keyword in _SECTION_KEYWORDS)


def parse_quantity(raw: str) -> tuple[int, int, bool]:
    noted = "noted" in raw.lower()
    cleaned = re.sub(r"\(.*?\)", "", raw)
    cleaned = re.sub(r"\[\[|\]\]", "", cleaned).strip()
    numbers = re.findall(r"\d[\d,]*", cleaned)
    values = [_to_int(n) for n in numbers]
    if not values:
        return 0, 0, noted
    return min(values), max(values), noted


def parse_rarity(raw: str) -> tuple[int | None, int | None, str | None]:
    text = raw.strip()
    if text.lower().startswith("always"):
        return 1, 1, None
    computed = rarity_from_expr(raw)
    if computed:
        return computed[0], computed[1], None
    if "{{#" in raw:
        return None, None, None
    fraction = _FRACTION_RE.search(raw)
    if fraction:
        return _to_int(fraction.group(1)), _to_int(fraction.group(2)), None
    match = _RARITY_RE.search(raw)
    if match:
        return _to_int(match.group(1)), _to_int(match.group(2)), None
    label = _MARKUP_RE.sub("", text).strip()
    if not label or label.lower() in _BLANK_RARITY:
        return None, None, None
    return None, None, label


def _parse_line(raw_line: str, group: str) -> ParsedDrop | None:
    inner = raw_line.strip().lstrip("{").rstrip("}")
    fields = parse_named_fields(split_template_fields(inner))
    name = fields.get("name", "").strip()
    if not name:
        return None
    low, high, noted = parse_quantity(fields.get("quantity", "1"))
    num, denom, label = parse_rarity(fields.get("rarity", ""))
    rolls = _to_int(fields.get("rolls", "1")) or 1
    return ParsedDrop(name, low, high, noted, num, denom, label, rolls, group)


def parse_drop_tables(wikitext: str) -> list[ParsedDrop]:
    text = strip_comments(wikitext)
    drops: list[ParsedDrop] = []
    in_drops = False
    group = ""
    for line in text.splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            in_drops = _is_drop_section(h2.group(1))
            group = ""
            continue
        hsub = _HSUB_RE.match(line)
        if hsub:
            group = hsub.group(1).strip()
            continue
        if in_drops and _DROPSLINE_RE.search(line):
            parsed = _parse_line(line, group)
            if parsed:
                drops.append(parsed)
    return drops
