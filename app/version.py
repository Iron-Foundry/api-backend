"""Runtime access to the version declared in pyproject.toml.

pyproject.toml is the single source of truth for the service version; nothing
else in the codebase hardcodes it. The file ships in the container image
(WORKDIR /app), so this resolves identically in development and production.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _read_version() -> str:
    with _PYPROJECT.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


VERSION = _read_version()
