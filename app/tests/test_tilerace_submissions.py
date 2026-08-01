from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from app.db.models import TileRaceEvent, TileRaceSubmission
from app.routers.tilerace._requirement_leaves import leaves
from app.routers.tilerace._submission_helpers import CLAIMED_STATUSES

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def _result(value: Any) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = 0
    result.scalars.return_value.all.return_value = []
    return result


def _load(mock_session: MagicMock, value: Any) -> None:
    mock_session.execute.return_value = _result(value)


def _load_sequence(mock_session: MagicMock, *values: Any) -> None:
    """One query at a time, so a multi-lookup route gets distinct answers."""
    mock_session.execute.side_effect = [_result(v) for v in values]


async def test_listing_submissions_requires_authentication(
    anon_client: AsyncClient,
) -> None:
    resp = await anon_client.get("/tilerace/events/12/submissions")
    assert resp.status_code == 401


async def test_listing_submissions_requires_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tilerace/events/12/submissions")
    assert resp.status_code == 403


async def test_listing_rejects_an_unknown_status(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/tilerace/events/12/submissions?status=maybe")
    assert resp.status_code == 400


async def test_context_404s_without_an_active_event(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load(mock_session, None)
    resp = await anon_client.get(
        "/tilerace/submissions/context", params={"discord_user_id": "123"}
    )
    assert resp.status_code == 404
    assert "No active tile race" in resp.json()["detail"]


async def test_context_403s_for_someone_with_no_team(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load_sequence(mock_session, TileRaceEvent(id=12, name="Race", cells=[]), None)
    resp = await anon_client.get(
        "/tilerace/submissions/context", params={"discord_user_id": "123"}
    )
    assert resp.status_code == 403


async def test_review_rejects_an_unknown_status(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load(mock_session, TileRaceSubmission(id=1, event_id=12))
    resp = await staff_client.patch(
        "/tilerace/events/12/submissions/1", json={"status": "maybe"}
    )
    assert resp.status_code == 400


async def test_thread_review_requires_a_reviewer(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load(mock_session, None)
    resp = await anon_client.post(
        "/tilerace/events/12/submissions/threads/555/review",
        json={"status": "approved"},
    )
    assert resp.status_code == 400
    assert "reviewed_by" in resp.json()["detail"]


async def test_thread_review_404s_when_the_thread_has_no_submissions(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    _load(mock_session, None)
    resp = await anon_client.post(
        "/tilerace/events/12/submissions/threads/555/review",
        json={"status": "approved", "reviewed_by": "777"},
    )
    assert resp.status_code == 404


async def test_creating_a_submission_needs_at_least_one_leaf(
    anon_client: AsyncClient,
) -> None:
    resp = await anon_client.post(
        "/tilerace/events/12/submissions",
        json={"discord_user_id": "1", "path_position": 1, "leaf_keys": []},
    )
    assert resp.status_code == 422


@pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)
def test_leaf_keys_match_the_shared_contract() -> None:
    """The keys the bot puts in a dropdown are the keys this side derives."""
    fixture = json.loads((_FIXTURES / "tilerace_submission.json").read_text())
    contract = fixture["context_response"]["leaves"]
    derived = leaves(
        {
            "kind": "and",
            "children": [
                {
                    "kind": "item",
                    "item_id": leaf["item_id"],
                    "quantity": 1,
                    "name": leaf["label"],
                }
                for leaf in contract
            ],
        }
    )
    assert [leaf["key"] for leaf in derived] == [leaf["key"] for leaf in contract]
    assert [leaf["label"] for leaf in derived] == [leaf["label"] for leaf in contract]
    assert set(CLAIMED_STATUSES) <= set(fixture["tile_statuses"])
