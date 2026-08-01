"""The staff half of submissions: the review queue on the website."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceSubmission
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._serializers import _serialize_submission
from ._submission_lookup import VALID_STATUSES
from ._submission_review import drop_submission, review_or_404
from .submission_schema import SubmissionReviewBody

router = APIRouter()
_VIEW = Depends(require_page_permission("tilerace.admin", "view"))
_EDIT = Depends(require_page_permission("tilerace.admin", "edit"))


@router.get("/events/{event_id}/submissions")
async def list_submissions(
    event_id: int,
    team_id: int | None = Query(None),
    status: str | None = Query(None),
    path_position: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _perm: None = _VIEW,
) -> dict[str, Any]:
    """List an event's proof submissions for review, newest first."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {VALID_STATUSES}")
    stmt = select(TileRaceSubmission).where(TileRaceSubmission.event_id == event_id)
    if team_id is not None:
        stmt = stmt.where(TileRaceSubmission.team_id == team_id)
    if status is not None:
        stmt = stmt.where(TileRaceSubmission.status == status)
    if path_position is not None:
        stmt = stmt.where(TileRaceSubmission.path_position == path_position)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(TileRaceSubmission.submitted_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "submissions": [_serialize_submission(s) for s in rows],
    }


@router.patch("/events/{event_id}/submissions/{submission_id}")
async def review_submission(
    event_id: int,
    submission_id: int,
    body: SubmissionReviewBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _EDIT,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Staff review. Approving keeps the claim, rejecting rolls the team back."""
    return await review_or_404(
        session, event_id, submission_id, body, int(current_user["sub"])
    )


@router.delete("/events/{event_id}/submissions/{submission_id}")
async def delete_submission(
    event_id: int,
    submission_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _EDIT,
) -> dict[str, Any]:
    """Remove a submission entirely and recompute the tile it belonged to.

    Rejecting keeps the audit trail; deleting is for a submission that should
    never have been logged, such as one filed against the wrong tile.
    """
    return await drop_submission(session, event_id, submission_id)
