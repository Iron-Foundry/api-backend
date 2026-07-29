"""Loading, visibility and serialisation for playlists.

Visibility has two distinct rules and they are deliberately not the same one:
a public playlist can be read and loaded by anyone, but only its owner may
change it. Every write path therefore goes through `require_owned`, never
through `require_visible`.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Playlist, PlaylistTrack

from ._schemas import PlaylistDetailOut, PlaylistOut, TrackIn, TrackOut

NOT_FOUND = "Playlist not found"
NOT_OWNER = "Only the owner can change this playlist"
DUPLICATE_NAME = "You already have a playlist with that name"


def _select(playlist_id: int) -> Any:
    return (
        select(Playlist)
        .where(Playlist.id == playlist_id)
        .options(selectinload(Playlist.tracks))
    )


async def load(session: AsyncSession, playlist_id: int) -> Playlist | None:
    return (await session.execute(_select(playlist_id))).scalar_one_or_none()


async def reload(session: AsyncSession, playlist_id: int) -> Playlist:
    """Re-read a playlist after a write, tracks and all.

    Two reasons this cannot be skipped. A just-committed playlist has never
    loaded its `tracks` collection, so serialising it would lazy-load - IO in a
    sync context, which raises MissingGreenlet under asyncio. And a playlist
    already in the identity map keeps whatever collection it had, so without
    `populate_existing` the response would describe the track list from before
    the write.
    """
    stmt = _select(playlist_id).execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one()


async def require_visible(
    session: AsyncSession, playlist_id: int, viewer_id: int | None
) -> Playlist:
    """A playlist the viewer is allowed to see: theirs, or any public one.

    A private playlist is reported as missing rather than forbidden, so its
    existence is not disclosed to someone who cannot see it.
    """
    playlist = await load(session, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if not playlist.is_public and playlist.owner_discord_id != viewer_id:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return playlist


async def require_owned(
    session: AsyncSession, playlist_id: int, owner_id: int
) -> Playlist:
    """A playlist the caller may modify. Public does not mean editable."""
    playlist = await load(session, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if playlist.owner_discord_id != owner_id:
        raise HTTPException(status_code=403, detail=NOT_OWNER)
    return playlist


def build_tracks(tracks: list[TrackIn], start: int = 0) -> list[PlaylistTrack]:
    """Rows for a track list, numbered in the order given.

    No `playlist_id`: these are appended to `Playlist.tracks`, so the ORM sets
    it. Inserting them directly would leave the already-loaded collection out
    of step with the table, and the response would be built from the stale one.
    """
    return [
        PlaylistTrack(
            position=start + position,
            source=track.source,
            identifier=track.identifier,
            title=track.title,
            author=track.author,
            duration_ms=track.duration_ms,
            isrc=track.isrc,
            uri=track.uri,
            artwork=track.artwork,
        )
        for position, track in enumerate(tracks)
    ]


def to_summary(playlist: Playlist) -> PlaylistOut:
    return PlaylistOut(
        id=playlist.id,
        owner_discord_id=str(playlist.owner_discord_id),
        name=playlist.name,
        is_public=playlist.is_public,
        track_count=len(playlist.tracks),
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


def to_detail(playlist: Playlist) -> PlaylistDetailOut:
    return PlaylistDetailOut(
        **to_summary(playlist).model_dump(),
        tracks=[
            TrackOut(
                position=track.position,
                source=track.source,
                identifier=track.identifier,
                title=track.title,
                author=track.author,
                duration_ms=track.duration_ms,
                isrc=track.isrc,
                uri=track.uri,
                artwork=track.artwork,
            )
            for track in sorted(playlist.tracks, key=lambda t: t.position)
        ],
    )
