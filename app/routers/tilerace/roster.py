from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceSignup, User
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import _serialize_signup, raids_kc_map
from ._roster_helpers import (
    clear_captain,
    entry_or_404,
    event_or_404,
    find_entry,
    primary_account,
    ranking_score,
    validate_team,
)
from .schemas import RosterAddBody, RosterPatch

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


@router.get("/events/{event_id}/roster/candidates")
async def list_candidates(
    event_id: int,
    search: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> list[dict[str, Any]]:
    """Clan members not on this event's roster yet, for the add picker."""
    await event_or_404(session, event_id)
    taken = select(TileRaceSignup.discord_user_id).where(
        TileRaceSignup.event_id == event_id
    )
    stmt = select(User.discord_user_id, User.discord_username, User.rsn).where(
        User.discord_user_id.notin_(taken)
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            User.rsn.ilike(pattern) | User.discord_username.ilike(pattern)
        )
    rows = await session.execute(
        stmt.order_by(User.rsn.asc().nulls_last()).limit(limit)
    )
    return [
        {
            "discord_user_id": str(row.discord_user_id),
            "discord_username": row.discord_username,
            "rsn": row.rsn,
        }
        for row in rows
    ]


@router.post("/events/{event_id}/roster", status_code=201)
async def add_roster_member(
    event_id: int,
    body: RosterAddBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Place a member on the roster on their behalf, signed up or not."""
    await event_or_404(session, event_id)
    await validate_team(session, event_id, body.team_id)
    user_id = int(body.discord_user_id)
    if await find_entry(session, event_id, user_id) is not None:
        raise HTTPException(409, "Already on this event's roster.")
    account = await primary_account(session, user_id)
    rsn = body.rsn or (account.rsn if account else None)
    if not rsn:
        raise HTTPException(422, "No linked account; supply an RSN.")
    entry = TileRaceSignup(
        event_id=event_id,
        team_id=body.team_id,
        discord_user_id=user_id,
        account_id=account.id if account else None,
        rsn=rsn,
        ranking_score=await ranking_score(session, rsn),
        wants_captain=False,
        is_captain=False,
        added_by_staff=True,
        signed_up_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.commit()
    return _serialize_signup(entry, await raids_kc_map(session, [entry]))


@router.patch("/events/{event_id}/roster/{discord_user_id}")
async def patch_roster_member(
    event_id: int,
    discord_user_id: int,
    body: RosterPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Move a member between teams, unassign them, or set them as captain.

    A team holds at most one captain: moving a captain to another team drops the
    badge unless the same request re-appoints them, and appointing a captain
    demotes whoever held it.
    """
    entry = await entry_or_404(session, event_id, discord_user_id)
    if "team_id" in body.model_fields_set and body.team_id != entry.team_id:
        await validate_team(session, event_id, body.team_id)
        entry.team_id = body.team_id
        entry.is_captain = False
    if body.is_captain is not None:
        if body.is_captain and entry.team_id is None:
            raise HTTPException(409, "Assign the member to a team first.")
        if body.is_captain:
            await clear_captain(session, entry.team_id, keep_id=entry.id)
        entry.is_captain = body.is_captain
    if body.rsn is not None:
        entry.rsn = body.rsn
        entry.ranking_score = await ranking_score(session, body.rsn)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "That team already has a captain.") from exc
    return _serialize_signup(entry, await raids_kc_map(session, [entry]))


@router.delete("/events/{event_id}/roster/{discord_user_id}")
async def remove_roster_member(
    event_id: int,
    discord_user_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Drop a member from the event entirely, team assignment and all."""
    entry = await entry_or_404(session, event_id, discord_user_id)
    await session.delete(entry)
    await session.commit()
    return {"ok": True}
