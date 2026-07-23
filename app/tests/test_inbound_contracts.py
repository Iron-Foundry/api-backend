"""Guard: shared cross-service fixtures validate against the api's inbound models.

The monorepo-root fixtures/ pins the exact payloads other services send. If an
inbound model drops or renames a field, constructing it from the fixture fails
here. Skipped when run outside the monorepo checkout (submodule-only CI).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers.ccdispatch import DiscordMessage
from app.routers.metrics._helpers import MetricReportBody

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

_missing = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


@_missing
def test_metrics_report_fixture_validates() -> None:
    data = json.loads((_FIXTURES / "metrics_report.json").read_text())
    body = MetricReportBody(**data)
    assert body.service_name == data["service_name"]
    assert body.metrics == data["metrics"]


@_missing
def test_cc_dispatch_fixture_validates() -> None:
    data = json.loads((_FIXTURES / "cc_dispatch.json").read_text())
    msg = DiscordMessage(**data)
    assert msg.sender == data["sender"]
    assert msg.message == data["message"]
    assert msg.rank == data["rank"]
