"""Regenerate the committed OpenAPI schema artifact.

The schema is the contract consumers (web-app, discord-server) pin to. Run this
whenever a router or response model changes:

    uv run python scripts/generate_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.main import app  # noqa: E402

_SCHEMA_PATH = _ROOT / "openapi.json"


def main() -> None:
    schema = app.openapi()
    _SCHEMA_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {_SCHEMA_PATH}")


if __name__ == "__main__":
    main()
