"""Importing a YouTube or YouTube Music playlist as a saved one.

Lavalink resolves the link, so this needs no bot and no voice channel - the
whole point is to build a library before anyone is listening. What is stored is
metadata, never audio: the ISRC is kept, so tracks re-resolve to playable audio
at play time rather than being pinned to source ids that rot.

A Spotify playlist, album or artist link cannot be imported, and that is not a
bug here: Spotify serves those endpoints only on behalf of a signed-in account.
`app/services/lavalink.py` says so in the error rather than this route guessing
at the link before trying it, since a single Spotify track link does resolve.

Mounted before the playlist router so `/playlists/import` is matched as itself
rather than tried as a `{playlist_id}`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Playlist
from app.dependencies import get_current_user, get_session
from app.services.lavalink import (
    IMPORT_LIMIT,
    SearchError,
    is_configured,
    load,
)

from ._helpers import DUPLICATE_NAME, build_tracks, reload, to_detail
from ._schemas import NAME_MAX, PlaylistDetailOut, TrackIn

router = APIRouter(prefix="/playlists")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[dict[str, Any], Depends(get_current_user)]

URL_MAX = 1000
UNAVAILABLE = "Importing is not configured on this server"
NOT_A_LINK = "Paste a link to a playlist"
NOTHING_FOUND = "Nothing could be loaded from that link"
FALLBACK_NAME = "Imported playlist"


class ImportPlaylistRequest(BaseModel):
    """A link to pull in, and optionally what to call the result."""

    url: str = Field(min_length=1, max_length=URL_MAX)
    # Defaults to whatever the source calls it, which is almost always right.
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    is_public: bool = False


@router.post("/import", status_code=201)
async def import_playlist(
    body: ImportPlaylistRequest, session: SessionDep, current_user: UserDep
) -> PlaylistDetailOut:
    """Save every track behind a playlist link as a new playlist.

    A link to a single track imports that one track, so a mistyped link makes a
    one-track playlist rather than an error nobody can act on.
    """
    if not is_configured():
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    if not body.url.strip().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail=NOT_A_LINK)

    try:
        result = await load(body.url, limit=IMPORT_LIMIT)
    except SearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result.tracks:
        raise HTTPException(status_code=404, detail=NOTHING_FOUND)

    playlist = Playlist(
        owner_discord_id=int(current_user["sub"]),
        name=body.name or result.playlist_name or FALLBACK_NAME,
        is_public=body.is_public,
    )
    playlist.tracks.extend(
        build_tracks([TrackIn.model_validate(track) for track in result.tracks])
    )
    session.add(playlist)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_NAME) from exc
    return to_detail(await reload(session, playlist.id))
