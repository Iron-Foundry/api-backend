"""The elevated permissions a team holds inside its own managed channels.

Toggles are event-wide and ride along in every provisioning command, so the bot
re-applies them onto the channels that already exist rather than rebuilding
them. A toggle that is off grants nothing; it never denies, so a permission the
role already has server-wide is left alone.
"""

from __future__ import annotations

from typing import Any

TOGGLES: tuple[str, ...] = (
    "pin_messages",
    "manage_messages",
    "mention_everyone",
    "manage_threads",
    "manage_channel",
    "voice_moderation",
)


def normalize(raw: dict[str, Any] | None) -> dict[str, bool]:
    """Every known toggle as a bool, with unknown keys dropped."""
    values = raw or {}
    return {name: bool(values.get(name)) for name in TOGGLES}
