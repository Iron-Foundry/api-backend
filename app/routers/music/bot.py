"""The read surface discord-utils uses.

The bot holds no user JWT - nobody logs into Discord through OAuth to press a
button - so it authenticates with the shared service key and names the Discord
user it is acting for. Visibility is then evaluated for that user exactly as it
would be on the web: their own playlists plus the public ones.

Read-only on purpose. Creating and editing playlists stays behind a real user
login on the web, so the service key can never be used to write on someone's
behalf.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Playlist
from app.dependencies import get_session, verify_metrics_key

from ._helpers import require_visible, to_detail, to_summary
from ._schemas import PlaylistDetailOut, PlaylistOut

router = APIRouter(
    prefix="/bot/{discord_user_id}/playlists",
    dependencies=[Depends(verify_metrics_key)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def playlists_for_user(
    discord_user_id: int,
    session: SessionDep,
    mine_only: Annotated[bool, Query()] = False,
) -> list[PlaylistOut]:
    """Playlists this Discord user can load: their own, plus the public ones."""
    stmt = select(Playlist).options(selectinload(Playlist.tracks))
    if mine_only:
        stmt = stmt.where(Playlist.owner_discord_id == discord_user_id)
    else:
        stmt = stmt.where(
            (Playlist.is_public.is_(True))
            | (Playlist.owner_discord_id == discord_user_id)
        )
    rows = (await session.execute(stmt.order_by(Playlist.name))).scalars().all()
    return [to_summary(row) for row in rows]


@router.get("/{playlist_id}")
async def playlist_for_user(
    discord_user_id: int, playlist_id: int, session: SessionDep
) -> PlaylistDetailOut:
    """One playlist with its tracks, if this user is allowed to see it."""
    playlist = await require_visible(session, playlist_id, discord_user_id)
    return to_detail(playlist)
