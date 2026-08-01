from __future__ import annotations

from typing import Any

from app.routers.tilerace._requirement_leaves import (
    is_satisfied,
    leaf_key,
    leaves,
)


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


def test_nested_tree_flattens_in_order() -> None:
    tree = {
        "kind": "and",
        "children": [
            _item(1, "First"),
            {"kind": "or", "children": [_item(2, "Second"), _text("Or this")]},
        ],
    }
    assert [e["label"] for e in leaves(tree)] == ["First", "Second", "Or this"]
