from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzySubmission, FrenzyTeam, User
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._constants import _VALID_SOURCES, _VALID_STATUSES, _VALID_SUBMISSION_TYPES
from ._scoring import _recompute_team_progress
from .schemas import SubmissionBody, SubmissionPatch

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy", "edit"))


def _submission_to_dict(
    sub: FrenzySubmission, reviewer: User | None = None
) -> dict[str, Any]:
    return {
        "id": sub.id,
        "event_id": sub.event_id,
        "team_id": sub.team_id,
        "discord_user_id": sub.discord_user_id,
        "player_rsn": sub.player_rsn,
        "source": sub.source,
        "submission_type": sub.submission_type,
        "payload": sub.payload,
        "status": sub.status,
        "auto_approved": sub.auto_approved,
        "reviewed_by": {
            "discord_user_id": reviewer.discord_user_id,
            "discord_username": reviewer.discord_username,
            "rsn": reviewer.rsn,
        }
        if reviewer
        else None,
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "review_notes": sub.review_notes,
        "submitted_at": sub.submitted_at.isoformat(),
        "created_at": sub.created_at.isoformat(),
    }


@router.get("/events/{event_id}/submissions")
async def list_submissions(
    event_id: int,
    team_id: int | None = Query(None),
    status: str | None = Query(None),
    submission_type: str | None = Query(None),
    source: str | None = Query(None),
    player_rsn: str | None = Query(None),
    auto_approved: bool | None = Query(None),
    submitted_after: datetime | None = Query(None),
    submitted_before: datetime | None = Query(None),
    q: str | None = Query(None, min_length=1),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """List an event's task submissions, filtered by team or review status."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    stmt = select(FrenzySubmission).where(FrenzySubmission.event_id == event_id)
    if team_id is not None:
        stmt = stmt.where(FrenzySubmission.team_id == team_id)
    if status is not None:
        if status not in _VALID_STATUSES:
            raise HTTPException(
                400, f"Invalid status. Must be one of: {_VALID_STATUSES}"
            )
        stmt = stmt.where(FrenzySubmission.status == status)
    if submission_type is not None:
        if submission_type not in _VALID_SUBMISSION_TYPES:
            raise HTTPException(400, "Invalid submission_type.")
        stmt = stmt.where(FrenzySubmission.submission_type == submission_type)
    if source is not None:
        if source not in _VALID_SOURCES:
            raise HTTPException(
                400, f"Invalid source. Must be one of: {_VALID_SOURCES}"
            )
        stmt = stmt.where(FrenzySubmission.source == source)
    if player_rsn is not None:
        stmt = stmt.where(FrenzySubmission.player_rsn.ilike(f"%{player_rsn}%"))
    if auto_approved is not None:
        stmt = stmt.where(FrenzySubmission.auto_approved == auto_approved)
    if submitted_after is not None:
        stmt = stmt.where(FrenzySubmission.submitted_at >= submitted_after)
    if submitted_before is not None:
        stmt = stmt.where(FrenzySubmission.submitted_at <= submitted_before)
    if q is not None:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                FrenzySubmission.player_rsn.ilike(like),
                FrenzySubmission.payload["item_name"].astext.ilike(like),
                FrenzySubmission.payload["source_name"].astext.ilike(like),
                FrenzySubmission.payload["name"].astext.ilike(like),
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(FrenzySubmission.submitted_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    reviewer_ids = {s.reviewed_by for s in rows if s.reviewed_by}
    reviewers: dict[int, User] = {}
    if reviewer_ids:
        reviewer_rows = (
            (
                await session.execute(
                    select(User).where(User.discord_user_id.in_(reviewer_ids))
                )
            )
            .scalars()
            .all()
        )
        reviewers = {u.discord_user_id: u for u in reviewer_rows}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "submissions": [
            _submission_to_dict(
                s, reviewers.get(s.reviewed_by) if s.reviewed_by is not None else None
            )
            for s in rows
        ],
    }


@router.post("/events/{event_id}/submissions", status_code=201)
async def create_submission(
    event_id: int,
    body: SubmissionBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a completed task with its proof for review."""
    if body.source not in _VALID_SOURCES:
        raise HTTPException(400, f"Invalid source. Must be one of: {_VALID_SOURCES}")
    if body.submission_type not in _VALID_SUBMISSION_TYPES:
        raise HTTPException(400, "Invalid submission_type.")

    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    team_id: int | None = body.payload.get("team_id")
    if team_id is None:
        raise HTTPException(400, "payload must include team_id.")
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.id == team_id, FrenzyTeam.event_id == event_id
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found in this event.")

    trusted: list[str] = event.trusted_sources or []
    auto_approve = body.source in trusted
    now = datetime.now(UTC)
    submitted_at = body.submitted_at or now

    sub = FrenzySubmission(
        event_id=event_id,
        team_id=team.id,
        discord_user_id=body.discord_user_id,
        player_rsn=body.player_rsn,
        source=body.source,
        submission_type=body.submission_type,
        payload={k: v for k, v in body.payload.items() if k != "team_id"},
        status="approved" if auto_approve else "pending",
        auto_approved=auto_approve,
        reviewed_by=int(current_user["sub"]) if auto_approve else None,
        reviewed_at=now if auto_approve else None,
        submitted_at=submitted_at,
        created_at=now,
    )
    session.add(sub)
    await session.flush()

    if auto_approve:
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"id": sub.id, "status": sub.status, "auto_approved": sub.auto_approved}


@router.patch("/events/{event_id}/submissions/{submission_id}")
async def patch_submission(
    event_id: int,
    submission_id: int,
    body: SubmissionPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve, reject, or amend a submission. Rescores the team."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {_VALID_STATUSES}")

    sub = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.id == submission_id,
                FrenzySubmission.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Submission not found.")

    prev_status = sub.status
    sub.status = body.status
    sub.review_notes = body.review_notes
    sub.reviewed_by = int(current_user["sub"])
    sub.reviewed_at = datetime.now(UTC)

    if body.status != prev_status and body.status in ("approved", "rejected"):
        team = (
            await session.execute(
                select(FrenzyTeam).where(FrenzyTeam.id == sub.team_id)
            )
        ).scalar_one()
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"ok": True, "status": sub.status}


@router.delete("/events/{event_id}/submissions/{submission_id}")
async def delete_submission(
    event_id: int,
    submission_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Delete a submission and remove its points from the team's score."""
    sub = (
        await session.execute(
            select(FrenzySubmission).where(
                FrenzySubmission.id == submission_id,
                FrenzySubmission.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Submission not found.")

    was_approved = sub.status == "approved"
    team_id = sub.team_id
    await session.delete(sub)
    await session.flush()

    if was_approved:
        team = (
            await session.execute(select(FrenzyTeam).where(FrenzyTeam.id == team_id))
        ).scalar_one()
        await _recompute_team_progress(session, team)

    await session.commit()
    return {"ok": True}
