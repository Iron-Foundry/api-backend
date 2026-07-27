"""Autouse fixture that initializes a mock WomRequestQueue for all tests.

The queue mock answers with an empty 200 response instead of a bare MagicMock, so
queue-routed WOM calls resolve offline rather than raising on await.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_wom_instance() -> Iterator[None]:
    import app.services.http.wom_queue as _wq

    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {}
    response.raise_for_status.return_value = None

    queue = MagicMock()
    queue.submit = AsyncMock(return_value=response)

    original = _wq._instance
    _wq._instance = queue
    yield
    _wq._instance = original
