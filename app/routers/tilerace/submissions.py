"""The service-key half of submissions: what discord-server calls."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceSubmission
from app.dependencies import get_current_user, get_session, verify_metrics_key

from ._requirement_leaves import leaf_catalog
from ._submission_helpers import apply_claim_state, tile_at
from ._submission_lookup import (
    active_submissions,
    submission_context,
    team_for_member,
)
from ._submission_review import review_thread
from .submission_schema import SubmissionCreateBody, SubmissionReviewBody
from .teams import _team_or_404

router = APIRouter()


@router.get("/submissions/context")
async def get_submission_context(
    discord_user_id: str,
    session: AsyncSession = Depends(get_session),
    _key: None = Depends(verify_metrics_key),
) -> dict[str, Any]:
    """Service-key lookup: what the caller's team currently has to prove.

    discord-server holds no tile race state, so the Submit button asks for the
    team, the tile it is standing on, and which leaves still need proof.
    """
    return await submission_context(session, int(discord_user_id))


@router.post("/events/{event_id}/submissions", status_code=201)
async def create_submissions(
    event_id: int,
    body: SubmissionCreateBody,
    session: AsyncSession = Depends(get_session),
    _key: None = Depends(verify_metrics_key),
) -> dict[str, Any]:
    """Service-key create: one row per requirement leaf the proof covers."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    user_id = int(body.discord_user_id)
    team, signup = await team_for_member(session, event_id, user_id)
    tile, requirement = await tile_at(session, event, body.path_position)
    catalog = {leaf["key"]: leaf for leaf in leaf_catalog(requirement, set())}
    unknown = [key for key in body.leaf_keys if key not in catalog]
    if unknown:
        raise HTTPException(400, f"Unknown requirement leaves: {', '.join(unknown)}")

    now = datetime.now(UTC)
    created: list[int] = []
    for key in body.leaf_keys:
        submission = TileRaceSubmission(
            event_id=event_id,
            team_id=team.id,
            path_position=body.path_position,
            tile_id=tile.id if tile else None,
            leaf_key=key,
            leaf_label=catalog[key]["label"],
            discord_user_id=user_id,
            player_rsn=signup.rsn,
            proof_urls=list(body.proof_urls),
            discord_thread_id=int(body.discord_thread_id)
            if body.discord_thread_id
            else None,
            status="pending",
            submitted_at=now,
            created_at=now,
        )
        session.add(submission)
        await session.flush()
        created.append(submission.id)

    status = await apply_claim_state(session, event, team, body.path_position)
    await session.commit()
    return {"ids": [str(i) for i in created], "tile_status": status}


@router.post("/events/{event_id}/submissions/threads/{thread_id}/review")
async def review_submission_thread(
    event_id: int,
    thread_id: int,
    body: SubmissionReviewBody,
    session: AsyncSession = Depends(get_session),
    _key: None = Depends(verify_metrics_key),
) -> dict[str, Any]:
    """Service-key review: the Approve/Reject buttons in a Discord thread.

    Staff judge the proof post as a whole, so every leaf submitted in that
    thread takes the same verdict.
    """
    if not body.reviewed_by:
        raise HTTPException(400, "reviewed_by is required.")
    return await review_thread(
        session, event_id, thread_id, body, int(body.reviewed_by)
    )


@router.get("/events/{event_id}/teams/{team_id}/tile-status")
async def get_tile_status(
    event_id: int,
    team_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Which leaves of a team's current tile still need proof."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    team = await _team_or_404(session, event_id, team_id)
    if event is None:
        raise HTTPException(404, "Event not found.")
    tile, requirement = await tile_at(session, event, team.position)
    covered = {
        s.leaf_key for s in await active_submissions(session, team_id, team.position)
    }
    return {
        "team_id": str(team.id),
        "path_position": team.position,
        "tile_id": str(tile.id) if tile else None,
        "leaves": leaf_catalog(requirement, covered),
    }
