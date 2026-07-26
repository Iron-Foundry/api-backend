"""Low-level wikitext helpers: comment stripping and template field parsing."""

from __future__ import annotations

import re

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def split_template_fields(inner: str) -> list[str]:
    """Split a template body on top-level pipes, ignoring pipes nested in
    {{...}}, [[...]] or {|...|} so DropsLine sub-templates stay intact."""
    fields: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    while i < len(inner):
        pair = inner[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            current.append(pair)
            i += 2
            continue
        if pair in ("}}", "]]"):
            depth = max(0, depth - 1)
            current.append(pair)
            i += 2
            continue
        char = inner[i]
        if char == "|" and depth == 0:
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    fields.append("".join(current))
    return fields


def parse_named_fields(fields: list[str]) -> dict[str, str]:
    """Turn `key=value` field strings into a dict; positional fields are ignored."""
    result: dict[str, str] = {}
    for field in fields:
        if "=" not in field:
            continue
        key, _, value = field.partition("=")
        result[key.strip().lower()] = value.strip()
    return result
