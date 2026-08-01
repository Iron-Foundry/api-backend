"""Evaluating a tile's requirement tree against the proof already submitted.

Kept apart from key derivation because these three answer a different question:
not "what are the leaves" but "what does the team still owe". The tree shape is
the whole point - a flat leaf count cannot tell "all of these" from "any one of
these", which is what made an ``or`` tile read as several outstanding items.
"""

from __future__ import annotations

from typing import Any

from ._requirement_leaves import leaves, next_key


def is_satisfied(
    requirement: dict[str, Any] | None,
    covered: set[str],
    _counter: dict[str, int] | None = None,
) -> bool:
    """Whether *covered* keys satisfy the tree.

    ``and`` needs every child, ``or`` needs one, ``not`` inverts. Duplicate
    leaves consume their ``#n`` suffixed keys in tree order, matching ``leaves``.
    """
    if requirement is None:
        return True
    counter = _counter if _counter is not None else {}
    kind = requirement.get("kind")
    if kind in ("and", "or"):
        results = [
            is_satisfied(c, covered, counter)
            for c in (requirement.get("children") or [])
        ]
        return all(results) if kind == "and" else any(results)
    if kind == "not":
        child = requirement.get("child")
        return not is_satisfied(child, covered, counter) if child else True
    return next_key(requirement, counter) in covered


def outstanding_count(
    requirement: dict[str, Any] | None,
    covered: set[str],
    _counter: dict[str, int] | None = None,
) -> int:
    """How many more leaves must be proved before the tile is satisfied.

    An ``or`` costs its cheapest branch, not the sum of them, so a tile asking
    for any one of three items is one submission outstanding rather than three.
    A ``not`` costs nothing: it is proved by leaving it alone, but its subtree is
    still walked so duplicate leaves keep the numbering ``leaves`` gave them.
    """
    if requirement is None:
        return 0
    counter = _counter if _counter is not None else {}
    kind = requirement.get("kind")
    if kind in ("and", "or"):
        costs = [
            outstanding_count(c, covered, counter)
            for c in (requirement.get("children") or [])
        ]
        if not costs:
            return 0
        return sum(costs) if kind == "and" else min(costs)
    if kind == "not":
        child = requirement.get("child")
        if child:
            outstanding_count(child, covered, counter)
        return 0
    return 0 if next_key(requirement, counter) in covered else 1


def leaf_catalog(
    requirement: dict[str, Any] | None, covered: set[str]
) -> list[dict[str, Any]]:
    """Every leaf of a tile, flagged with its submission and whether it helps.

    ``needed`` is true only when proving that leaf would bring the tile closer
    to satisfied. Every branch of an unproved ``or`` is needed, because any one
    of them finishes it; the moment one branch lands the rest stop being asked
    for, and a leaf under a ``not`` is never asked for at all.
    """
    remaining = outstanding_count(requirement, covered)
    catalog: list[dict[str, Any]] = []
    for leaf in leaves(requirement):
        is_covered = leaf["key"] in covered
        helps = (
            not is_covered
            and outstanding_count(requirement, covered | {leaf["key"]}) < remaining
        )
        catalog.append({**leaf, "covered": is_covered, "needed": helps})
    return catalog
