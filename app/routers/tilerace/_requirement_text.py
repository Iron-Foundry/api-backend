"""A requirement tree rendered as plain markdown bullets.

The bot holds no tile race state, so the wording of a tile's requirements is
settled here rather than re-derived from a tree discord-server would otherwise
have to understand.
"""

from __future__ import annotations

from typing import Any

from ._requirement_leaves import leaf_label


def requirement_lines(requirement: dict[str, Any] | None) -> list[str]:
    """Indented bullets, with ``and`` / ``or`` spelled out in words.

    A top-level ``and`` is flattened: the common tile asks for a handful of
    items and does not need an "All of:" heading above them.
    """
    if not requirement:
        return []
    if requirement.get("kind") == "and":
        lines: list[str] = []
        for child in requirement.get("children") or []:
            lines.extend(_render(child, 0))
        return lines
    return _render(requirement, 0)


def _render(node: dict[str, Any] | None, depth: int) -> list[str]:
    if not node:
        return []
    pad = "  " * depth
    kind = node.get("kind")
    if kind in ("and", "or"):
        children = node.get("children") or []
        if len(children) == 1:
            return _render(children[0], depth)
        if not children:
            return []
        lines = [f"{pad}- {'All of:' if kind == 'and' else 'Any one of:'}"]
        for child in children:
            lines.extend(_render(child, depth + 1))
        return lines
    if kind == "not":
        child = node.get("child")
        if not child:
            return []
        return [f"{pad}- Without:", *_render(child, depth + 1)]
    return [f"{pad}- {leaf_label(node)}"]
