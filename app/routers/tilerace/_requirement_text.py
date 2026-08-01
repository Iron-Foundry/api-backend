"""A requirement tree rendered as plain markdown bullets.

The bot holds no tile race state, so the wording of a tile's requirements is
settled here rather than re-derived from a tree discord-server would otherwise
have to understand. That includes the shape: a flat list of every leaf reads as
"prove all of these", which is wrong the moment a tile offers alternatives.
"""

from __future__ import annotations

from typing import Any

from ._requirement_leaves import leaf_label, next_key


def requirement_lines(
    requirement: dict[str, Any] | None, covered: set[str] | None = None
) -> list[str]:
    """Indented bullets, with ``and`` / ``or`` spelled out in words.

    A top-level ``and`` is flattened: the common tile asks for a handful of
    items and does not need an "All of:" heading above them. Leaves listed in
    *covered* are struck through and marked as already submitted.
    """
    if not requirement:
        return []
    counter: dict[str, int] = {}
    proved = covered or set()
    if requirement.get("kind") == "and":
        lines: list[str] = []
        for child in requirement.get("children") or []:
            lines.extend(_render(child, 0, proved, counter))
        return lines
    return _render(requirement, 0, proved, counter)


def _render(
    node: dict[str, Any] | None,
    depth: int,
    covered: set[str],
    counter: dict[str, int],
) -> list[str]:
    if not node:
        return []
    pad = "  " * depth
    kind = node.get("kind")
    if kind in ("and", "or"):
        children = node.get("children") or []
        if len(children) == 1:
            return _render(children[0], depth, covered, counter)
        if not children:
            return []
        lines = [f"{pad}- {'All of:' if kind == 'and' else 'Any one of:'}"]
        for child in children:
            lines.extend(_render(child, depth + 1, covered, counter))
        return lines
    if kind == "not":
        child = node.get("child")
        if not child:
            return []
        return [f"{pad}- Without:", *_render(child, depth + 1, covered, counter)]
    label = leaf_label(node)
    if next_key(node, counter) in covered:
        return [f"{pad}- ~~{label}~~ (submitted)"]
    return [f"{pad}- {label}"]
