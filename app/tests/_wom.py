"""Autouse fixture that initializes a mock WomRequestQueue for all tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_wom_instance():
    import app.services.http.wom_queue as _wq

    original = _wq._instance
    _wq._instance = MagicMock()
    yield
    _wq._instance = original
