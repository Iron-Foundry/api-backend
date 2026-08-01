"""Stable keys for the leaves of a tile's requirement tree.

Keys are derived from leaf content rather than tree position so that reordering
a tile's items, or editing an unrelated branch, leaves existing submissions
pointing at the same leaf.
"""

from __future__ import annotations

import hashlib
from typing import Any


def leaf_key(node: dict[str, Any]) -> str:
    kind = node.get("kind")
    if kind == "item":
        return f"item:{int(node.get('item_id', 0))}:{int(node.get('quantity', 1))}"
    digest = hashlib.sha1(
        str(node.get("text", "")).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return f"text:{digest[:8]}"


def leaf_label(node: dict[str, Any]) -> str:
    if node.get("kind") != "item":
        return str(node.get("text", "")) or "Requirement"
    name = str(node.get("name", "")) or f"Item {node.get('item_id', 0)}"
    quantity = int(node.get("quantity", 1))
    return f"{name} x{quantity}" if quantity > 1 else name


def leaves(requirement: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Every leaf of the tree, each as ``{key, label, item_id, kind}``.

    Repeated identical leaves get a ``#n`` suffix so a tile asking for the same
    item twice still needs two submissions.
    """
    collected: list[dict[str, Any]] = []
    _walk(requirement, collected)
    seen: dict[str, int] = {}
    for entry in collected:
        base = entry["key"]
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            entry["key"] = f"{base}#{count}"
    return collected


def _walk(node: dict[str, Any] | None, out: list[dict[str, Any]]) -> None:
    if not node:
        return
    kind = node.get("kind")
    if kind in ("and", "or"):
        for child in node.get("children") or []:
            _walk(child, out)
        return
    if kind == "not":
        _walk(node.get("child"), out)
        return
    out.append(
        {
            "key": leaf_key(node),
            "label": leaf_label(node),
            "kind": str(kind or "text"),
            "item_id": int(node.get("item_id", 0)) if kind == "item" else None,
        }
    )


def next_key(node: dict[str, Any], counter: dict[str, int]) -> str:
    """The key of the next occurrence of *node*, tracking duplicates in order."""
    base = leaf_key(node)
    count = counter.get(base, 0)
    counter[base] = count + 1
    return f"{base}#{count}" if count else base
