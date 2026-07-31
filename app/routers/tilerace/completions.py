from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceCompletion, TileRaceEvent, TileRaceTeam
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._serializers import _serialize_completion
from .schemas import CompletionBody

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


@router.get("/events/{event_id}/completions")
async def list_completions(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List which board positions each team has completed."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    rows = (
        (
            await session.execute(
                select(TileRaceCompletion).where(
                    TileRaceCompletion.event_id == event_id
                )
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_completion(c) for c in rows]


@router.put("/events/{event_id}/teams/{team_id}/completions/{path_position}")
async def set_completion(
    event_id: int,
    team_id: int,
    path_position: int,
    body: CompletionBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a board position complete or incomplete for a team."""
    team = (
        await session.execute(
            select(TileRaceTeam).where(
                TileRaceTeam.id == team_id, TileRaceTeam.event_id == event_id
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")
    existing = (
        await session.execute(
            select(TileRaceCompletion).where(
                TileRaceCompletion.team_id == team_id,
                TileRaceCompletion.path_position == path_position,
            )
        )
    ).scalar_one_or_none()
    if body.completed and existing is None:
        session.add(
            TileRaceCompletion(
                event_id=event_id,
                team_id=team_id,
                path_position=path_position,
                completed_by=int(current_user["sub"]),
                completed_at=datetime.now(UTC),
            )
        )
    elif not body.completed and existing is not None:
        await session.delete(existing)
    await session.commit()
    return {"ok": True, "completed": body.completed}
