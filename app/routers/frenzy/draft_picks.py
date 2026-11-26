"""The public draft view and its live socket, the picks, and the staff moves after it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import FrenzyDraft, FrenzyEvent, FrenzySignup
from app.dependencies import get_current_user, get_session, get_valkey
from app.services.frenzy_draft_live import draft_hub, publish_draft_change
from app.services.page_permissions import (
    require_page_permission,
    user_has_page_permission,
)

from ._draft_roster import finish_if_done, pool_of, sync_participants
from ._draft_view import build_view, draft_or_404, event_signups
from ._snake import snake_slot
from .draft_schemas import DraftMoveBody, DraftPickBody, DraftView

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


@router.get("/events/{event_id}/draft")
async def get_draft(
    event_id: int, session: AsyncSession = Depends(get_session)
) -> DraftView:
    """The draft as everyone sees it: teams in drawn order and the pool."""
    return await build_view(session, await draft_or_404(session, event_id))


@router.websocket("/draft/live")
async def draft_live(websocket: WebSocket) -> None:
    """Send `{"type": "draft", "event_id": n}` whenever a draft changes."""
    await websocket.accept()
    socket_id = draft_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        draft_hub.disconnect(socket_id)


async def _may_pick(
    session: AsyncSession, draft: FrenzyDraft, user_id: int, signups: list[FrenzySignup]
) -> bool:
    """The captain whose turn it is may pick, and so may frenzy staff."""
    slot = snake_slot(draft.next_pick, len(draft.team_ids))
    captain = next(s for s in signups if s.id == draft.captain_ids[slot])
    if captain.discord_user_id == user_id:
        return True
    return await user_has_page_permission(user_id, "frenzy.admin", "edit", session)


@router.post("/events/{event_id}/draft/picks")
async def make_pick(
    event_id: int,
    body: DraftPickBody,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DraftView:
    """Put a pool signup on the team whose turn it is."""
    draft = await draft_or_404(session, event_id)
    if draft.state != "picking":
        raise HTTPException(409, "The draft is not taking picks.")
    if body.pick_number != draft.next_pick:
        raise HTTPException(409, f"Pick {body.pick_number} is already made.")
    signups = await event_signups(session, event_id)
    if not await _may_pick(session, draft, int(current_user["sub"]), signups):
        raise HTTPException(403, "It is another captain's turn.")
    signup = next((s for s in pool_of(draft, signups) if s.id == body.signup_id), None)
    if signup is None:
        raise HTTPException(422, "That signup is not in the pool.")
    signup.team_id = draft.team_ids[snake_slot(draft.next_pick, len(draft.team_ids))]
    signup.pick_number = draft.next_pick
    signup.pick_kind = "drafted"
    draft.next_pick += 1
    await session.flush()
    await finish_if_done(session, draft)
    draft.updated_at = datetime.now(UTC)
    await sync_participants(session, event_id)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return await build_view(session, draft)


@router.post("/events/{event_id}/draft/moves")
async def move_member(
    event_id: int,
    body: DraftMoveBody,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> DraftView:
    """Move a member to another team after the draft and before the event starts."""
    draft = await draft_or_404(session, event_id)
    if draft.state != "complete":
        raise HTTPException(409, "Members move only after the draft is complete.")
    event = await session.get(FrenzyEvent, event_id)
    if event and event.starts_at and event.starts_at <= datetime.now(UTC):
        raise HTTPException(409, "The event has started.")
    if body.team_id not in draft.team_ids:
        raise HTTPException(422, "That team is not part of this draft.")
    signup = await session.get(FrenzySignup, body.signup_id)
    if signup is None or signup.event_id != event_id or signup.team_id is None:
        raise HTTPException(422, "That signup is not on a team of this draft.")
    if signup.pick_kind == "captain":
        raise HTTPException(409, "A captain stays with their team.")
    signup.team_id = body.team_id
    await session.flush()
    await sync_participants(session, event_id)
    await session.commit()
    await publish_draft_change(valkey, event_id)
    return await build_view(session, draft)
