"""The wire shapes of a frenzy event signup."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_ID = Field(default=None, ge=1)


def _known_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown IANA time zone: {name}") from exc
    return name


Timezone = Annotated[str, Field(max_length=64), AfterValidator(_known_zone)]


class FrenzySignupBody(BaseModel):
    """A signup request; no `account_id` means the member's primary account.

    `timezone` is the member's IANA time zone, as their browser reports it.
    """

    model_config = ConfigDict(extra="forbid")

    account_id: int | None = _ID
    wants_captain: bool = False
    timezone: Timezone | None = None


class FrenzySignupPatch(BaseModel):
    """Moves a signup to another linked account, or changes the opt-in or time zone."""

    model_config = ConfigDict(extra="forbid")

    account_id: int | None = _ID
    wants_captain: bool | None = None
    timezone: Timezone | None = None


class MyFrenzySignup(BaseModel):
    """The caller's own signup, as the public event view shows it."""

    account_id: int | None
    rsn: str
    wants_captain: bool
    timezone: str | None
    signed_up_at: datetime


class FrenzySignupOut(BaseModel):
    """One signup in the staff list."""

    id: int
    wants_captain: bool
    discord_user_id: str
    discord_username: str | None
    account_id: int | None
    rsn: str
    signed_up_at: datetime


class FrenzySignupList(BaseModel):
    items: list[FrenzySignupOut]
    total: int
