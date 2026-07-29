"""The Valkey key names the music surface reads, and how their values decode.

discord-utils owns every key here; nothing on this side writes to them. The
names mirror `discord-utils/music/keys.py` and are pinned from both sides by
`fixtures/music_bridge.json` rather than shared as a package, because the two
services are deployed independently - a rename on one side has to fail a test
rather than quietly read an empty list forever.

Valkey answers in bytes unless the client is told otherwise, so decoding lives
here too: every reader wants the same `str`.
"""

from __future__ import annotations

import json
from typing import Any

SESSION = "music:session:{voice_channel_id}"
QUEUE = "music:queue:{voice_channel_id}"
ACTIVITY = "music:activity:{voice_channel_id}"
HISTORY = "music:history:{voice_channel_id}"
VOICE = "music:voice:{voice_channel_id}"
SESSION_PATTERN = "music:session:*"

COMMANDS_CHANNEL = "music:commands"
STATE_CHANNEL = "music:state"

QUEUE_PAGE = 500


def text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def mapping(raw: dict[Any, Any]) -> dict[str, str]:
    return {text(key): text(value) for key, value in raw.items()}


def entries(raw: list[Any]) -> list[dict[str, Any]]:
    """The readable JSON items in a capped list, skipping any that are not.

    An unreadable entry is dropped rather than raised on: one bad item written
    by an older bot must not take the whole feed down with it.
    """
    found: list[dict[str, Any]] = []
    for item in raw:
        try:
            found.append(json.loads(text(item)))
        except ValueError:
            continue
    return found
