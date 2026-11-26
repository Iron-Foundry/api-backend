from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KillRateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kills_per_hour: float = Field(gt=0, le=100_000)


class KillRateOut(BaseModel):
    source: str
    kills_per_hour: float
    set_by: int
    set_by_name: str | None
    updated_at: datetime


class KillRatePage(BaseModel):
    items: list[KillRateOut]
    total: int
    limit: int
    offset: int


class RateOut(BaseModel):
    metric: str
    kind: str
    rate: float
    payload: dict[str, Any]
    updated_at: datetime
