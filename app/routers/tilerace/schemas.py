from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from .modifier_schema import Modifier
from .requirement_schema import RequirementNode


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class Pad(BaseModel):
    cell_x: int
    cell_y: int
    width: int = 1
    height: int = 1
    trigger: Modifier | None = None

    @field_validator("width", "height")
    @classmethod
    def _size(cls, v: int) -> int:
        return _clamp(v, 1, 50)


class TileBody(BaseModel):
    title: str
    description: str = ""
    icon_url: str | None = None
    icon_source: str = "wiki"
    items: list = []
    requirement: RequirementNode | None = None
    tags: list[str] = []


class TilePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    icon_url: str | None = None
    icon_source: str | None = None
    items: list | None = None
    requirement: RequirementNode | None = None
    tags: list[str] | None = None


class EventBody(BaseModel):
    name: str
    grid_cols: int = 10
    grid_rows: int = 5
    dice_count: int = 1
    dice_sides: int = 6
    background_url: str | None = None
    start_pad: Pad | None = None
    end_pad: Pad | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("grid_cols")
    @classmethod
    def _cols(cls, v: int) -> int:
        return _clamp(v, 2, 50)

    @field_validator("grid_rows")
    @classmethod
    def _rows(cls, v: int) -> int:
        return _clamp(v, 2, 30)

    @field_validator("dice_count")
    @classmethod
    def _dice_count(cls, v: int) -> int:
        return _clamp(v, 1, 5)

    @field_validator("dice_sides")
    @classmethod
    def _dice_sides(cls, v: int) -> int:
        return _clamp(v, 1, 20)


class EventPatch(BaseModel):
    name: str | None = None
    grid_cols: int | None = None
    grid_rows: int | None = None
    dice_count: int | None = None
    dice_sides: int | None = None
    background_url: str | None = None
    fog_of_war: bool | None = None
    is_finished: bool | None = None
    cells: list | None = None
    start_pad: Pad | None = None
    end_pad: Pad | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("grid_cols")
    @classmethod
    def _cols(cls, v: int | None) -> int | None:
        return None if v is None else _clamp(v, 2, 50)

    @field_validator("grid_rows")
    @classmethod
    def _rows(cls, v: int | None) -> int | None:
        return None if v is None else _clamp(v, 2, 30)

    @field_validator("dice_count")
    @classmethod
    def _dice_count(cls, v: int | None) -> int | None:
        return None if v is None else _clamp(v, 1, 5)

    @field_validator("dice_sides")
    @classmethod
    def _dice_sides(cls, v: int | None) -> int | None:
        return None if v is None else _clamp(v, 1, 20)


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
    roll: int | None = None


class FogBody(BaseModel):
    enabled: bool


class CompletionBody(BaseModel):
    completed: bool


class SabotageBody(BaseModel):
    action: str
    target_team_id: int
    amount: int = 0
