from __future__ import annotations

from typing import Any

from app.routers.tilerace._requirement_leaves import leaf_key, leaves
from app.routers.tilerace._requirement_state import (
    is_satisfied,
    leaf_catalog,
    outstanding_count,
)
from app.routers.tilerace._requirement_text import requirement_lines


def _item(item_id: int, name: str = "", quantity: int = 1) -> dict[str, Any]:
    return {
        "kind": "item",
        "item_id": item_id,
        "quantity": quantity,
        "name": name or f"Item {item_id}",
    }


def _text(text: str) -> dict[str, Any]:
    return {"kind": "text", "text": text}


def test_a_single_item_tile_has_one_leaf() -> None:
    tree = _item(11832, "Bandos chestplate")
    entries = leaves(tree)
    assert [e["key"] for e in entries] == ["item:11832:1"]
    assert entries[0]["label"] == "Bandos chestplate"
    assert entries[0]["item_id"] == 11832


def test_quantity_is_part_of_the_key_and_the_label() -> None:
    entries = leaves(_item(565, "Blood rune", quantity=500))
    assert entries[0]["key"] == "item:565:500"
    assert entries[0]["label"] == "Blood rune x500"


def test_keys_survive_reordering_the_children() -> None:
    a = {"kind": "and", "children": [_item(1), _item(2), _item(3)]}
    b = {"kind": "and", "children": [_item(3), _item(1), _item(2)]}
    assert sorted(e["key"] for e in leaves(a)) == sorted(e["key"] for e in leaves(b))


def test_duplicate_leaves_get_distinct_keys() -> None:
    tree = {"kind": "and", "children": [_item(4151), _item(4151)]}
    assert [e["key"] for e in leaves(tree)] == ["item:4151:1", "item:4151:1#1"]


def test_text_leaves_key_off_their_text() -> None:
    assert leaf_key(_text("Fire cape")) != leaf_key(_text("Infernal cape"))
    assert leaf_key(_text("Fire cape")) == leaf_key(_text("Fire cape"))


def test_and_needs_every_leaf() -> None:
    tree = {"kind": "and", "children": [_item(1), _item(2)]}
    assert not is_satisfied(tree, {"item:1:1"})
    assert is_satisfied(tree, {"item:1:1", "item:2:1"})


def test_or_needs_only_one_branch() -> None:
    tree = {"kind": "or", "children": [_item(1), _item(2)]}
    assert is_satisfied(tree, {"item:2:1"})
    assert not is_satisfied(tree, set())


def test_duplicate_leaves_need_both_submissions() -> None:
    tree = {"kind": "and", "children": [_item(4151), _item(4151)]}
    assert not is_satisfied(tree, {"item:4151:1"})
    assert is_satisfied(tree, {"item:4151:1", "item:4151:1#1"})


def test_or_branches_do_not_shift_duplicate_numbering() -> None:
    tree = {
        "kind": "and",
        "children": [
            {"kind": "or", "children": [_item(7), _item(7)]},
            _item(7),
        ],
    }
    keys = [e["key"] for e in leaves(tree)]
    assert keys == ["item:7:1", "item:7:1#1", "item:7:1#2"]
    assert is_satisfied(tree, {"item:7:1#1", "item:7:1#2"})
    assert not is_satisfied(tree, {"item:7:1", "item:7:1#1"})


def test_not_inverts() -> None:
    tree = {"kind": "not", "child": _item(1)}
    assert is_satisfied(tree, set())
    assert not is_satisfied(tree, {"item:1:1"})


def test_a_tile_without_a_requirement_is_always_satisfied() -> None:
    assert is_satisfied(None, set())
    assert leaves(None) == []


def test_an_any_of_tile_owes_one_submission_not_one_per_branch() -> None:
    tree = {"kind": "or", "children": [_item(1), _item(2), _item(3)]}
    assert outstanding_count(tree, set()) == 1
    assert outstanding_count(tree, {"item:2:1"}) == 0


def test_every_branch_of_an_unproved_any_of_is_offered() -> None:
    tree = {"kind": "or", "children": [_item(1), _item(2), _item(3)]}
    assert [leaf["needed"] for leaf in leaf_catalog(tree, set())] == [True, True, True]


def test_one_proved_branch_stops_the_others_being_asked_for() -> None:
    tree = {"kind": "or", "children": [_item(1), _item(2), _item(3)]}
    catalog = leaf_catalog(tree, {"item:2:1"})

    assert [leaf["needed"] for leaf in catalog] == [False, False, False]
    assert [leaf["covered"] for leaf in catalog] == [False, True, False]


def test_an_all_of_still_owes_every_unproved_leaf() -> None:
    tree = {"kind": "and", "children": [_item(1), _item(2), _item(3)]}
    assert outstanding_count(tree, {"item:1:1"}) == 2
    assert [leaf["needed"] for leaf in leaf_catalog(tree, {"item:1:1"})] == [
        False,
        True,
        True,
    ]


def test_an_any_of_branch_that_needs_two_items_counts_the_cheaper_branch() -> None:
    tree = {
        "kind": "or",
        "children": [
            {"kind": "and", "children": [_item(1), _item(2)]},
            _item(3),
        ],
    }
    assert outstanding_count(tree, set()) == 1
    assert outstanding_count(tree, {"item:1:1"}) == 1


def test_a_not_is_never_owed_and_never_offered() -> None:
    tree = {
        "kind": "and",
        "children": [_item(1), {"kind": "not", "child": _item(2)}],
    }
    assert outstanding_count(tree, set()) == 1
    assert [leaf["needed"] for leaf in leaf_catalog(tree, set())] == [True, False]


def test_an_empty_tile_owes_nothing() -> None:
    assert outstanding_count(None, set()) == 0
    assert leaf_catalog(None, set()) == []


def test_the_rendered_lines_spell_out_the_choice_and_mark_what_is_in() -> None:
    tree = {
        "kind": "and",
        "children": [
            _item(1, "Rune bar"),
            {"kind": "or", "children": [_item(2, "Dragon axe"), _item(3, "Infernal")]},
        ],
    }
    assert requirement_lines(tree, {"item:2:1"}) == [
        "- Rune bar",
        "- Any one of:",
        "  - ~~Dragon axe~~ (submitted)",
        "  - Infernal",
    ]


def test_rendered_lines_strike_the_right_one_of_a_duplicate_pair() -> None:
    tree = {"kind": "and", "children": [_item(7, "Coal"), _item(7, "Coal")]}
    assert requirement_lines(tree, {"item:7:1#1"}) == [
        "- Coal",
        "- ~~Coal~~ (submitted)",
    ]


def test_nested_tree_flattens_in_order() -> None:
    tree = {
        "kind": "and",
        "children": [
            _item(1, "First"),
            {"kind": "or", "children": [_item(2, "Second"), _text("Or this")]},
        ],
    }
    assert [e["label"] for e in leaves(tree)] == ["First", "Second", "Or this"]
