from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TileBody(BaseModel):
    title: str
    description: str = ""
    icon_url: str | None = None
    icon_source: str = "wiki"
    items: list = []
    tags: list[str] = []


class TilePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    icon_url: str | None = None
    icon_source: str | None = None
    items: list | None = None
    tags: list[str] | None = None


class EventBody(BaseModel):
    name: str
    grid_cols: int = 10
    grid_rows: int = 5
    background_url: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventPatch(BaseModel):
    name: str | None = None
    grid_cols: int | None = None
    grid_rows: int | None = None
    background_url: str | None = None
    fog_of_war: bool | None = None
    cells: list | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class TeamBody(BaseModel):
    name: str
    slug: str
    icon_type: str = "item"
    icon_url: str = ""
    color: str = "#888888"


class TeamPatch(BaseModel):
    name: str | None = None
    slug: str | None = None
    icon_type: str | None = None
    icon_url: str | None = None
    color: str | None = None
    position: int | None = None


class RollBody(BaseModel):
    roll: int


class FogBody(BaseModel):
    enabled: bool
