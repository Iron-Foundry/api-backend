"""Verdicts on a submission, and the board state each one leaves behind."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceSubmission, TileRaceTeam

from ._submission_helpers import apply_claim_state
from ._submission_lookup import VALID_STATUSES
from .submission_schema import SubmissionReviewBody


async def review_or_404(
    session: AsyncSession,
    event_id: int,
    submission_id: int,
    body: SubmissionReviewBody,
    reviewer_id: int,
) -> dict[str, Any]:
    """Set one submission's status and recompute the tile it belongs to."""
    _require_status(body.status)
    submission = await _submission_or_404(session, event_id, submission_id)
    event, team = await _event_and_team(session, event_id, submission.team_id)

    submission.status = body.status
    submission.review_notes = body.review_notes
    submission.reviewed_by = reviewer_id
    submission.reviewed_at = datetime.now(UTC)
    await session.flush()

    tile_status = await apply_claim_state(
        session, event, team, submission.path_position
    )
    await session.commit()
    return {
        "ok": True,
        "status": submission.status,
        "tile_status": tile_status,
        "team_position": team.position,
        "furthest_position": team.furthest_position,
    }


async def review_thread(
    session: AsyncSession,
    event_id: int,
    thread_id: int,
    body: SubmissionReviewBody,
    reviewer_id: int,
) -> dict[str, Any]:
    """Review every submission made in one Discord thread at once.

    A single proof post can cover several requirement leaves, and staff judge the
    post, not each leaf, so the thread is the unit the buttons act on.
    """
    _require_status(body.status)
    rows = list(
        (
            await session.execute(
                select(TileRaceSubmission).where(
                    TileRaceSubmission.event_id == event_id,
                    TileRaceSubmission.discord_thread_id == thread_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(404, "No submissions found for that thread.")
    event, _team = await _event_and_team(session, event_id, rows[0].team_id)
    now = datetime.now(UTC)
    for row in rows:
        row.status = body.status
        row.review_notes = body.review_notes
        row.reviewed_by = reviewer_id
        row.reviewed_at = now
    await session.flush()

    statuses: list[str] = []
    for team_id, path_position in {(r.team_id, r.path_position) for r in rows}:
        team = (
            await session.execute(
                select(TileRaceTeam).where(TileRaceTeam.id == team_id)
            )
        ).scalar_one()
        statuses.append(await apply_claim_state(session, event, team, path_position))
    await session.commit()
    return {
        "ok": True,
        "status": body.status,
        "reviewed": len(rows),
        "tile_status": statuses[0] if statuses else None,
    }


async def drop_submission(
    session: AsyncSession, event_id: int, submission_id: int
) -> dict[str, Any]:
    """Delete one submission, then recompute the tile it was proving."""
    submission = await _submission_or_404(session, event_id, submission_id)
    team_id = submission.team_id
    path_position = submission.path_position
    event, team = await _event_and_team(session, event_id, team_id)
    await session.delete(submission)
    await session.flush()

    tile_status = await apply_claim_state(session, event, team, path_position)
    await session.commit()
    return {"ok": True, "tile_status": tile_status, "team_position": team.position}


def _require_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {VALID_STATUSES}")


async def _submission_or_404(
    session: AsyncSession, event_id: int, submission_id: int
) -> TileRaceSubmission:
    submission = (
        await session.execute(
            select(TileRaceSubmission).where(
                TileRaceSubmission.id == submission_id,
                TileRaceSubmission.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(404, "Submission not found.")
    return submission


async def _event_and_team(
    session: AsyncSession, event_id: int, team_id: int
) -> tuple[TileRaceEvent, TileRaceTeam]:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one()
    team = (
        await session.execute(select(TileRaceTeam).where(TileRaceTeam.id == team_id))
    ).scalar_one()
    return event, team
