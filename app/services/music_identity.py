"""What counts as the same recording.

Its own module because it is the one judgement in the stats pipeline that can be
wrong without anything erroring: everything else is arithmetic, but two keys for
one song, or one key for two, is a "top tracks" list nobody can trust and no
migration can repair after the fact.
"""

from __future__ import annotations

import hashlib


def track_key(isrc: str, title: str, author: str, length_ms: int) -> tuple[str, bool]:
    """Stable identity for a recording, ISRC first.

    Keying on the source identifier would split one song across Spotify and
    YouTube and turn "top tracks" into a list of duplicates. Without an ISRC the
    fallback is a digest of the normalised metadata: weaker, but it at least
    agrees with itself across sources that name the track the same way.

    The duration is bucketed to whole seconds, since the same recording is
    routinely reported a few milliseconds apart by two sources.
    """
    if isrc:
        return f"isrc:{isrc.upper()}", True
    seed = f"{title.strip().casefold()}|{author.strip().casefold()}|{length_ms // 1000}"
    return f"md:{hashlib.sha256(seed.encode()).hexdigest()[:32]}", False
