from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceTeam
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from .schemas import SabotageBody

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


async def _team(
    session: AsyncSession, event_id: int, team_id: int
) -> TileRaceTeam | None:
    return (
        await session.execute(
            select(TileRaceTeam).where(
                TileRaceTeam.id == team_id, TileRaceTeam.event_id == event_id
            )
        )
    ).scalar_one_or_none()


@router.post("/events/{event_id}/teams/{team_id}/sabotage")
async def sabotage(
    event_id: int,
    team_id: int,
    body: SabotageBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    actor = await _team(session, event_id, team_id)
    target = await _team(session, event_id, body.target_team_id)
    if actor is None or target is None:
        raise HTTPException(404, "Team not found.")
    now = datetime.now(timezone.utc)
    if body.action == "steal_progress":
        moved = min(body.amount, target.position)
        target.position = target.position - moved
        actor.position = actor.position + moved
        actor.updated_at = now
    elif body.action == "block":
        effects = dict(target.pending_effects or {})
        effects["skip_next"] = True
        target.pending_effects = effects
    else:
        raise HTTPException(400, "Unknown sabotage action.")
    target.updated_at = now
    await session.commit()
    return {"ok": True, "action": body.action}
