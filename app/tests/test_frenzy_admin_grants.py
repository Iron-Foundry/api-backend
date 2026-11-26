"""Migration 0067 carries frenzy edit grants onto frenzy.admin without duplicates."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0067_frenzy_admin_grants.py"
)


def _merged_grants() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0067", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.merged_grants


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ({"frenzy": {"edit": ["mod"]}}, ["mod"]),
        ({"frenzy": {"edit": ["mod"]}, "frenzy.admin": {"edit": ["mod"]}}, ["mod"]),
        (
            {"frenzy": {"edit": ["mod", "dep"]}, "frenzy.admin": {"edit": ["owner"]}},
            ["owner", "mod", "dep"],
        ),
        ({"frenzy.admin": {"edit": ["owner"]}}, ["owner"]),
    ],
)
def test_frenzy_edit_roles_reach_frenzy_admin(
    pages: dict[str, Any], expected: list[str]
) -> None:
    merged = _merged_grants()({"pages": pages}, "frenzy", "frenzy.admin")
    assert merged["pages"]["frenzy.admin"]["edit"] == expected
