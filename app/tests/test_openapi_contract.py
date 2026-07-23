"""Guard: the committed openapi.json is the contract consumers pin to.

If a router or response model changes without regenerating the artifact, this
fails and points at the regen command. See scripts/generate_openapi.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def test_openapi_artifact_is_current() -> None:
    assert _SCHEMA_PATH.exists(), (
        "openapi.json missing - run: uv run python scripts/generate_openapi.py"
    )
    committed = json.loads(_SCHEMA_PATH.read_text())
    assert committed == app.openapi(), (
        "openapi.json is stale - regenerate it: "
        "uv run python scripts/generate_openapi.py"
    )
