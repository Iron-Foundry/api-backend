from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TemplateBody(BaseModel):
    name: str
    description: str | None = None
    tiers: dict = {}
    activities: list = []
    milestones: dict = {}
    multipliers: list = []
    total_point_cap: int = 0


class CalculatePointsBody(BaseModel):
    tiers: dict
    total_point_cap: int


class EventBody(BaseModel):
    name: str
    template_id: int
    wom_comp_id: int | None = None
    leaderboard_metrics: list[str] = []
    trusted_sources: list[str] = []
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventPatch(BaseModel):
    name: str | None = None
    wom_comp_id: int | None = None
    leaderboard_metrics: list[str] | None = None
    trusted_sources: list[str] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class SubmissionBody(BaseModel):
    discord_user_id: int
    player_rsn: str
    source: str
    submission_type: str
    payload: dict
    submitted_at: datetime | None = None


class SubmissionPatch(BaseModel):
    status: str
    review_notes: str | None = None


class TeamBody(BaseModel):
    name: str
    slug: str
    icon_url: str | None = None
    sort_order: int = 0


class TeamPatch(BaseModel):
    name: str | None = None
    icon_url: str | None = None
    sort_order: int | None = None
    item_progress: dict | None = None
    activity_progress: dict | None = None
    milestone_progress: dict | None = None
