"""The wire shapes of a frenzy captain draft."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DraftMode = Literal["full", "top_picks"]
DraftState = Literal["setup", "drawn", "picking", "complete"]
PickKind = Literal["captain", "drafted", "auto"]


class DraftSetupBody(BaseModel):
    """The mode, the top picks per captain and the captains, as signup ids."""

    model_config = ConfigDict(extra="forbid")

    mode: DraftMode
    top_picks: int = Field(default=5, ge=1, le=100)
    captain_signup_ids: list[int] = Field(min_length=2, max_length=50)

    @field_validator("captain_signup_ids")
    @classmethod
    def _distinct(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids):
            raise ValueError("A signup can captain one team only.")
        return ids


class DraftPickBody(BaseModel):
    """One pick; `pick_number` must be the draft's next pick."""

    model_config = ConfigDict(extra="forbid")

    signup_id: int = Field(ge=1)
    pick_number: int = Field(ge=1)


class DraftMoveBody(BaseModel):
    """Moves a drafted member to another team of the event."""

    model_config = ConfigDict(extra="forbid")

    signup_id: int = Field(ge=1)
    team_id: int = Field(ge=1)


class DraftMember(BaseModel):
    """One signup as the draft shows it; rank and points are null without a ranking.

    `timezone` is the IANA zone the member signed up from, null when unknown.
    """

    signup_id: int
    rsn: str
    timezone: str | None
    rank: str | None
    points: int | None
    wants_captain: bool
    pick_number: int | None
    pick_kind: PickKind | None


class DraftTeam(BaseModel):
    team_id: int
    name: str
    captain: DraftMember
    captain_discord_user_id: str
    members: list[DraftMember]


class DraftView(BaseModel):
    """The whole draft: teams in drawn order, the pool strongest first."""

    event_id: int
    mode: DraftMode
    top_picks: int
    state: DraftState
    next_pick: int
    picking_team_id: int | None
    captains: list[DraftMember]
    teams: list[DraftTeam]
    pool: list[DraftMember]
