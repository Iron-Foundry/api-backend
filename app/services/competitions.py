"""Competition management service - create, edit, delete WOM group competitions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.http import WiseOldManHandler


class CompetitionTeam(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    participants: list[str] = Field(default_factory=list)


class CreateCompetitionInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    metric: str
    starts_at: datetime
    ends_at: datetime
    type: Literal["classic", "team"] = "classic"
    participants: list[str] | None = None
    teams: list[CompetitionTeam] | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "CreateCompetitionInput":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

    @model_validator(mode="after")
    def validate_participant_fields(self) -> "CreateCompetitionInput":
        if self.type == "team":
            if not self.teams:
                raise ValueError("teams required when type is 'team'")
            if self.participants:
                raise ValueError("participants must be empty when type is 'team'")
        else:
            if self.teams:
                raise ValueError("teams must be empty when type is 'classic'")
        return self


class EditCompetitionInput(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    metric: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "EditCompetitionInput":
        if all(
            v is None for v in [self.title, self.metric, self.starts_at, self.ends_at]
        ):
            raise ValueError("at least one field must be provided")
        return self


async def create_competition(
    data: CreateCompetitionInput,
    *,
    group_id: str | int,
    api_key: str | None = None,
    discord_contact: str | None = None,
) -> dict:
    payload: dict = {
        "title": data.title,
        "metric": data.metric,
        "startsAt": data.starts_at.isoformat(),
        "endsAt": data.ends_at.isoformat(),
    }
    if data.type == "team" and data.teams:
        payload["teams"] = [t.model_dump() for t in data.teams]
    elif data.participants:
        payload["participants"] = data.participants
    else:
        payload["groupId"] = int(group_id)

    async with WiseOldManHandler(
        api_key=api_key, discord_contact=discord_contact
    ) as wom:
        return await wom.create_competition(payload)


async def edit_competition(
    comp_id: int,
    data: EditCompetitionInput,
    *,
    group_key: str,
    api_key: str | None = None,
    discord_contact: str | None = None,
) -> dict:
    payload: dict = {"verificationCode": group_key}
    if data.title is not None:
        payload["title"] = data.title
    if data.metric is not None:
        payload["metric"] = data.metric
    if data.starts_at is not None:
        payload["startsAt"] = data.starts_at.isoformat()
    if data.ends_at is not None:
        payload["endsAt"] = data.ends_at.isoformat()

    async with WiseOldManHandler(
        api_key=api_key, discord_contact=discord_contact
    ) as wom:
        return await wom.edit_competition(comp_id, payload)


async def delete_competition(
    comp_id: int,
    *,
    group_key: str,
    api_key: str | None = None,
    discord_contact: str | None = None,
) -> None:
    payload = {"verificationCode": group_key}
    async with WiseOldManHandler(
        api_key=api_key, discord_contact=discord_contact
    ) as wom:
        await wom.delete_competition(comp_id, payload)
