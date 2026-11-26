"""The staff steps of a frenzy captain draft: set up, draw the order, start, reset."""

from __future__ import annotations

import random
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import FrenzyDraft, FrenzyEvent, FrenzyTeam
from app.dependencies import get_session, get_valkey
from app.services.frenzy_draft_live import publish_draft_change
from app.services.page_permissions import require_page_permission

from ._draft_roster import (
    clear_assignment,
    create_captain_teams,
    sync_participants,
)
from ._draft_view import build_view, draft_or_404, event_signups
from .draft_schemas import DraftSetupBody, DraftView

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


def _require_state(draft: FrenzyDraft, state: str) -> None:
    if draft.state != state:
        raise HTTPException(409, f"The draft is {draft.state}, not {state}.")


@router.put("/events/{event_id}/draft")
async def set_up_draft(
    event_id: int,
    body: DraftSetupBody,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> DraftView:
    """Choose the mode, the top picks per captain and the captains."""
    if await session.get(FrenzyEvent, event_id) is None:
        raise HTTPException(404, "Event not found.")
    ids = {s.id for s in await event_signups(session, event_id)}
    if not set(body.captain_signup_ids) <= ids:
        raise HTTPException(422, "Every captain must be a signup of this event.")
    draft = (
        await session.execute(
            select(FrenzyDraft).where(FrenzyDraft.event_id == event_id)
        )
    ).scalar_one_or_none()
    if draft is None:
        draft = FrenzyDraft(event_id=event_id, state="setup", next_pick=1)
        session.add(draft)
    _require_state(draft, "setup")
    draft.mode = body.mode
    draft.top_picks = body.top_picks
    draft.captain_ids = body.captain_signup_ids
    draft.updated_at = datetime.now(UTC)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return await build_view(session, draft)


@router.post("/events/{event_id}/draft/draw")
async def draw_order(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> DraftView:
    """Draw a random round-1 order and make one team per captain."""
    draft = await draft_or_404(session, event_id)
    _require_state(draft, "setup")
    existing = await session.execute(
        select(FrenzyTeam.id).where(FrenzyTeam.event_id == event_id).limit(1)
    )
    if existing.first() is not None:
        raise HTTPException(409, "The event already has teams.")
    by_id = {s.id: s for s in await event_signups(session, event_id)}
    order = random.sample(draft.captain_ids, k=len(draft.captain_ids))
    draft.captain_ids = order
    draft.team_ids = await create_captain_teams(
        session, event_id, [by_id[c] for c in order]
    )
    draft.state = "drawn"
    draft.updated_at = datetime.now(UTC)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return await build_view(session, draft)


@router.post("/events/{event_id}/draft/start")
async def start_draft(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> DraftView:
    """Open pick 1."""
    draft = await draft_or_404(session, event_id)
    _require_state(draft, "drawn")
    draft.state = "picking"
    draft.next_pick = 1
    draft.updated_at = datetime.now(UTC)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return await build_view(session, draft)


@router.delete("/events/{event_id}/draft", status_code=204)
async def reset_draft(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> Response:
    """Remove the draft and the teams its draw made; every signup returns to the pool."""
    draft = await draft_or_404(session, event_id)
    for signup in await event_signups(session, event_id):
        clear_assignment(signup)
    await session.flush()
    if draft.team_ids:
        await session.execute(
            delete(FrenzyTeam).where(FrenzyTeam.id.in_(draft.team_ids))
        )
    await session.delete(draft)
    await sync_participants(session, event_id)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return Response(status_code=204)
