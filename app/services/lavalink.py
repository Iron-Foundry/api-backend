"""Resolving a query into tracks, straight from Lavalink.

Lavalink's `/v4/loadtracks` is plain HTTP with a password header
(`lavalink-repo/docs/api/rest.md:87-101`), so searching needs no player, no
voice connection and no bot. That is what lets the website build a playlist with
nothing playing: a search is a lookup, not playback.

Only metadata is returned. The `encoded` audio handle is deliberately dropped -
discord-utils re-resolves at play time anyway, and echoing it would put playable
audio into a web page.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

LAVALINK_URI = os.getenv("LAVALINK_URI", "")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "")

REQUEST_TIMEOUT_SECONDS = 10.0
RESULTS_SHOWN = 25
# An import takes the whole thing, up to what a playlist may hold.
IMPORT_LIMIT = 500

# The prefixes Lavalink documents, plus the one LavaSrc adds for Spotify.
SOURCE_PREFIXES = {
    "youtube": "ytsearch:",
    "youtubemusic": "ytmsearch:",
    "soundcloud": "scsearch:",
    "spotify": "spsearch:",
}
DEFAULT_SOURCE = "spotify"

# A URL is loaded as itself; prefixing it would search for the text of the link.
URL_PREFIXES = ("http://", "https://")

# Lavalink reports a generic message and buries the real one in the stack trace.
_CAUSE = re.compile(r"Caused by: [\w.$]*(?:Exception|Error): (.+)")

SPOTIFY_HOST = "open.spotify.com"
# Spotify answers 401 "Valid user authentication required" for playlists and 403
# for albums and artist pages when the caller holds only app credentials. Both
# arrive here as a bare status inside the stack trace.
_SPOTIFY_REFUSALS = ("channel info is 401", "channel info is 403")

SPOTIFY_NEEDS_A_USER = (
    "Spotify only lets an app read a playlist, album or artist page on behalf of"
    " a signed-in Spotify account, and this server holds app credentials rather"
    " than anyone's account - so Spotify links to those cannot be imported."
    " Individual Spotify track links still work. For a whole playlist, import"
    " its YouTube or YouTube Music link instead, or search for the tracks and"
    " add them."
)
SPOTIFY_GENERATED = (
    "Spotify will not let any app read the playlists it generates itself -"
    " Discover Weekly, Release Radar, Daily Mix and the editorial 'This Is...'"
    " lists, whose links all start open.spotify.com/playlist/37i9dQZ. Import the"
    " same playlist from YouTube or YouTube Music instead."
)


class SearchError(RuntimeError):
    """The search could not be run, or Lavalink refused it."""


@dataclass(slots=True)
class LoadResult:
    """What a query resolved to.

    `playlist_name` is set only when the link was a playlist, which is what an
    import names the new playlist after.
    """

    tracks: list[dict[str, Any]] = field(default_factory=list)
    playlist_name: str | None = None


def is_configured() -> bool:
    """Whether searching is available at all on this deployment."""
    return bool(LAVALINK_URI and LAVALINK_PASSWORD)


def build_identifier(query: str, source: str) -> str:
    """What to hand Lavalink: a bare URL, or a prefixed search."""
    text = query.strip()
    if text.startswith(URL_PREFIXES):
        return text
    return f"{SOURCE_PREFIXES.get(source, SOURCE_PREFIXES[DEFAULT_SOURCE])}{text}"


async def load_tracks(
    query: str, source: str = DEFAULT_SOURCE, *, transport: Any = None
) -> list[dict[str, Any]]:
    """Track info dicts for a query, capped at what a search offers."""
    return (await load(query, source, transport=transport)).tracks


async def load(
    query: str,
    source: str = DEFAULT_SOURCE,
    *,
    limit: int = RESULTS_SHOWN,
    transport: Any = None,
) -> LoadResult:
    """Resolve a query or a link, keeping the playlist name when there is one."""
    if not is_configured():
        raise SearchError("Search is not available - Lavalink is not configured")

    params = {"identifier": build_identifier(query, source)}
    try:
        async with httpx.AsyncClient(
            base_url=LAVALINK_URI,
            timeout=REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        ) as http:
            response = await http.get(
                "/v4/loadtracks",
                params=params,
                headers={"Authorization": LAVALINK_PASSWORD},
            )
    except httpx.HTTPError as exc:
        logger.warning("Music: Lavalink search failed: {}", exc)
        raise SearchError("The audio service is not reachable right now") from exc

    if response.status_code >= 400:
        logger.warning("Music: Lavalink answered HTTP {}", response.status_code)
        raise SearchError("The audio service refused that search")
    return _result_of(response.json(), limit, query)


def _result_of(body: dict[str, Any], limit: int, query: str) -> LoadResult:
    """Flatten a load result into plain track info, whatever its type.

    A search returns a list, a link returns one track, and a link to a playlist
    returns a container with the tracks inside it. All three are the same thing
    to a caller who only wants something to queue.
    """
    load_type = body.get("loadType")
    data = body.get("data")

    if load_type == "empty" or data is None:
        return LoadResult()
    if load_type == "error":
        raise _load_error(data, query)

    name: str | None = None
    if load_type == "track":
        found = [data]
    elif load_type == "playlist":
        found = data.get("tracks", [])
        name = (data.get("info") or {}).get("name") or None
    else:
        found = data if isinstance(data, list) else []
    return LoadResult(
        tracks=[_info(track) for track in found[:limit]], playlist_name=name
    )


def _load_error(data: dict[str, Any], query: str) -> SearchError:
    """Turn a load failure into something the person who pasted the link can act on.

    Lavalink's top-level `message` is lavaplayer's generic "Something went wrong
    while looking up the track"; the reason worth reading is a `Caused by`
    further down the stack trace, and the deepest one is the specific one. Where
    that reason is a platform restriction rather than a mistake, it is replaced
    by what it means and by what will work instead - a bare "Server responded
    with an error" or an HTTP status tells nobody anything.
    """
    trace = data.get("causeStackTrace") or ""
    if "generated playlists" in trace:
        return SearchError(SPOTIFY_GENERATED)
    if SPOTIFY_HOST in query and any(hit in trace for hit in _SPOTIFY_REFUSALS):
        return SearchError(SPOTIFY_NEEDS_A_USER)
    return SearchError(f"The audio service could not load that: {_reason(data)}")


def _reason(data: dict[str, Any]) -> str:
    causes = _CAUSE.findall(data.get("causeStackTrace") or "")
    if causes:
        return causes[-1].strip()
    return data.get("message") or "Unknown error"


def _info(track: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = track.get("info", {})
    return {
        "source": info.get("sourceName", ""),
        "identifier": info.get("identifier", ""),
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "duration_ms": info.get("length", 0),
        "isrc": info.get("isrc"),
        "uri": info.get("uri"),
        "artwork": info.get("artworkUrl"),
        "is_stream": bool(info.get("isStream", False)),
    }
