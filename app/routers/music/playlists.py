"""Playlist CRUD.

api-backend owns playlists because the web is the CRUD surface for them.
discord-utils reads them over HTTP rather than keeping a second copy.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Playlist
from app.dependencies import get_current_user, get_optional_user, get_session

from ._helpers import (
    DUPLICATE_NAME,
    build_tracks,
    reload,
    require_owned,
    require_visible,
    to_detail,
    to_summary,
)
from ._schemas import (
    CreatePlaylistRequest,
    PlaylistDetailOut,
    PlaylistOut,
    TracksRequest,
    UpdatePlaylistRequest,
)

router = APIRouter(prefix="/playlists")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[dict[str, Any], Depends(get_current_user)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]

Scope = Literal["mine", "public", "all"]


def _user_id(user: dict[str, Any] | None) -> int | None:
    return int(user["sub"]) if user else None


@router.get("")
async def list_playlists(
    session: SessionDep,
    current_user: OptionalUserDep,
    scope: Annotated[Scope, Query()] = "all",
) -> list[PlaylistOut]:
    """List playlists: your own, the public ones, or both."""
    viewer_id = _user_id(current_user)
    if scope == "mine" and viewer_id is None:
        return []

    stmt = select(Playlist).options(selectinload(Playlist.tracks))
    stmt = stmt.where(_visibility(scope, viewer_id))
    rows = (await session.execute(stmt.order_by(Playlist.name))).scalars().all()
    return [to_summary(row) for row in rows]


def _visibility(scope: Scope, viewer_id: int | None) -> Any:
    """The filter for what this viewer is allowed to see in this scope.

    An anonymous caller asking for everything gets the public ones, which is
    the same set as asking for public explicitly.
    """
    if scope == "mine":
        return Playlist.owner_discord_id == viewer_id
    if scope == "public" or viewer_id is None:
        return Playlist.is_public.is_(True)
    return or_(
        Playlist.is_public.is_(True),
        Playlist.owner_discord_id == viewer_id,
    )


@router.get("/{playlist_id}")
async def get_playlist(
    playlist_id: int, session: SessionDep, current_user: OptionalUserDep
) -> PlaylistDetailOut:
    """A playlist and its tracks. Public ones are readable by anyone."""
    playlist = await require_visible(session, playlist_id, _user_id(current_user))
    return to_detail(playlist)


@router.post("", status_code=201)
async def create_playlist(
    body: CreatePlaylistRequest, session: SessionDep, current_user: UserDep
) -> PlaylistDetailOut:
    """Create a playlist, optionally with its tracks in one call."""
    playlist = Playlist(
        owner_discord_id=int(current_user["sub"]),
        name=body.name,
        is_public=body.is_public,
    )
    playlist.tracks.extend(build_tracks(body.tracks))
    session.add(playlist)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_NAME) from exc
    return to_detail(await reload(session, playlist.id))


@router.patch("/{playlist_id}")
async def update_playlist(
    playlist_id: int,
    body: UpdatePlaylistRequest,
    session: SessionDep,
    current_user: UserDep,
) -> PlaylistOut:
    """Rename a playlist or change whether it is public. Owner only."""
    owner_id = int(current_user["sub"])
    playlist = await require_owned(session, playlist_id, owner_id)

    if body.name is not None:
        playlist.name = body.name
    if body.is_public is not None:
        playlist.is_public = body.is_public

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_NAME) from exc
    return to_summary(await reload(session, playlist_id))


@router.delete("/{playlist_id}", status_code=204)
async def delete_playlist(
    playlist_id: int, session: SessionDep, current_user: UserDep
) -> Response:
    """Delete a playlist and its tracks. Owner only."""
    playlist = await require_owned(session, playlist_id, int(current_user["sub"]))
    await session.delete(playlist)
    await session.commit()
    return Response(status_code=204)


@router.put("/{playlist_id}/tracks")
async def replace_tracks(
    playlist_id: int,
    body: TracksRequest,
    session: SessionDep,
    current_user: UserDep,
) -> PlaylistDetailOut:
    """Replace the whole track list. Owner only.

    A whole-list replace rather than per-track edits, because that is what
    saving a queue or reordering one actually is, and it keeps positions
    contiguous without a renumbering pass.
    """
    playlist = await require_owned(session, playlist_id, int(current_user["sub"]))

    # delete-orphan on the relationship removes the old rows, but a single
    # flush emits the inserts before the deletes, so the new position 0 would
    # collide with the old one. Flushing the clear first orders them.
    playlist.tracks.clear()
    await session.flush()
    playlist.tracks.extend(build_tracks(body.tracks))
    await session.commit()
    return to_detail(await reload(session, playlist_id))


@router.post("/{playlist_id}/tracks")
async def append_tracks(
    playlist_id: int,
    body: TracksRequest,
    session: SessionDep,
    current_user: UserDep,
) -> PlaylistDetailOut:
    """Add tracks to the end of a playlist. Owner only."""
    playlist = await require_owned(session, playlist_id, int(current_user["sub"]))

    playlist.tracks.extend(build_tracks(body.tracks, start=len(playlist.tracks)))
    await session.commit()
    return to_detail(await reload(session, playlist_id))
