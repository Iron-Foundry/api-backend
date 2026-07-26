from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SourceOut(BaseModel):
    slug: str
    display_name: str
    category: str
    wiki_page: str
    reward_kind: str | None
    updated_at: datetime


class DropOut(BaseModel):
    item_id: int | None
    item_name: str
    quantity_low: int
    quantity_high: int
    noted: bool
    rarity_num: int | None
    rarity_denom: int | None
    rarity_text: str | None
    rolls: int
    drop_group: str
    ge_price: int | None = None


class SourceListOut(SourceOut):
    drop_count: int


class SourceDetailOut(SourceOut):
    drops: list[DropOut]


class ItemSourceOut(BaseModel):
    source: SourceOut
    drop: DropOut


class RateOut(BaseModel):
    metric: str
    kind: str
    rate: float
    payload: dict
    updated_at: datetime
