"""Finding something to play, without needing anything to be playing.

Lavalink resolves a query over plain HTTP, so this needs no bot, no voice
channel and no session. That is deliberate: a playlist is built long before
anyone is listening, and gating search on a live session would make the library
unusable exactly when it is most useful.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.services.lavalink import (
    DEFAULT_SOURCE,
    SOURCE_PREFIXES,
    SearchError,
    is_configured,
    load_tracks,
)

from ._live_schemas import SearchResult

router = APIRouter(prefix="/search")

UserDep = Annotated[dict[str, Any], Depends(get_current_user)]

QUERY_MAX = 300
UNAVAILABLE = "Search is not configured on this server"


@router.get("")
async def search_tracks(
    current_user: UserDep,
    q: Annotated[str, Query(min_length=1, max_length=QUERY_MAX)],
    source: Annotated[str, Query()] = DEFAULT_SOURCE,
) -> list[SearchResult]:
    """Resolve a query, or a link, into tracks that can be queued or saved.

    A link is loaded as itself; anything else is searched on the named source.
    A link to a playlist comes back as all of its tracks.
    """
    if not is_configured():
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    if source not in SOURCE_PREFIXES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source {source!r}; try {', '.join(SOURCE_PREFIXES)}",
        )

    try:
        found = await load_tracks(q, source)
    except SearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [SearchResult.model_validate(track) for track in found]
