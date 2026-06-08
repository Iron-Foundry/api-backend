"""Competition cache helpers for the WOM handler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class _CachedComp:
    data: dict
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime | None  # None = infinite TTL (finished or upcoming)


def _comp_status(entry: _CachedComp) -> str:
    now = datetime.now(timezone.utc)
    if now < entry.starts_at:
        return "upcoming"
    if now <= entry.ends_at:
        return "ongoing"
    return "finished"


def _ttl_for(now: datetime, starts_at: datetime, ends_at: datetime) -> datetime | None:
    if now > ends_at:
        return None  # finished - cache forever
    if now >= starts_at:
        return now + timedelta(minutes=5)  # ongoing - 5 min TTL
    return None  # upcoming - no expiry


def parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
