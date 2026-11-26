"""The loot rate shapes that the OSRSClans API answers with."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import computed_field

from app.services.osrsclans.images import ImageAsk, osrs_image_url
from app.services.osrsclans.wire_model import OsrsClansModel

# `foundry` is never an OSRSClans value: Foundry sets it on a row whose rate
# comes from `source_kill_rates`.
KillRateSource = Literal[
    "wom", "droptracker", "clue_scroll", "fixed", "item_drop", "superior", "foundry"
]
LootCategory = Literal["raid", "boss", "minigame", "clue", "skilling", "monster"]


class LootLine(OsrsClansModel):
    """One line of a Wiki drop table, with its rarity as the Wiki writes it.

    `quantity_low` and `quantity_high` are the numbers of the `quantity` range,
    null where the Wiki gives none. `group` is the heading of the drop table.
    """

    rarity: str
    alt_rarity: str | None
    rolls: float
    quantity: str
    quantity_low: float | None = None
    quantity_high: float | None = None
    noted: bool = False
    approximate: bool
    group: str | None = None


class LootSkill(OsrsClansModel):
    """The level that a skilling pet or clue nest chance is computed at."""

    kind: str
    level_needed: int | None
    level: int | None


class LootRate(OsrsClansModel):
    """One item from one drop source, with the source's kill rate and the item's price.

    `chance` is the chance of at least one drop per kill, and null where the Wiki
    gives a word for the rarity. `per_purple` marks a raid unique whose chance is
    per purple. `chance_per_raid` is that chance times the mean uniques a raid at
    the asked `points` and `raid_level`. A null kill rate is unknown.
    `collection_log` marks an item on the collection log page that this source
    fills, and `collection_log_page` names that page.
    """

    item_id: int | None
    item_name: str
    source: str
    page: str
    section: str | None
    category: LootCategory | None
    drop_type: str
    group: str | None
    lines: list[LootLine]
    chance: float | None
    alt_chance: float | None
    per_purple: bool
    uniques_per_raid: float | None
    chance_per_raid: float | None
    kills_per_hour: float | None
    kills_per_hour_ironman: float | None
    kill_rate_source: KillRateSource | None
    wom_metric: str | None
    skill: LootSkill | None
    ge_price: int | None
    high_alchemy: int | None
    collection_log: bool
    collection_log_page: str | None
    read_at: datetime

    @computed_field
    @property
    def image_url(self) -> str | None:
        if self.item_id is None:
            return None
        return osrs_image_url(ImageAsk("items", self.item_id))


class LootRatePage(OsrsClansModel):
    """One window of loot rates, with the count of all rows that match."""

    items: list[LootRate]
    total: int
    limit: int
    offset: int


class LootSource(OsrsClansModel):
    """One drop source, with its kill rate and its count of loot rate rows.

    `source` is the value that `/reference/loot-rates?source=` takes.
    `collection_log_page` is the collection log page the source fills, and
    `collection_log_rows` counts the source's rows on it.
    """

    source: str
    page: str
    section: str | None
    category: LootCategory | None
    drop_types: list[str]
    rows: int
    kills_per_hour: float | None
    kills_per_hour_ironman: float | None
    kill_rate_source: KillRateSource | None
    wom_metric: str | None
    collection_log_page: str | None
    collection_log_rows: int


class LootSourcePage(OsrsClansModel):
    """One window of drop sources, with the count of all sources that match."""

    items: list[LootSource]
    total: int
    limit: int
    offset: int
