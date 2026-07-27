from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LootSource(Base):
    """A boss, activity, clue, or minigame that has a reference drop table."""

    __tablename__ = "loot_sources"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    wiki_page: Mapped[str] = mapped_column(Text, nullable=False)
    reward_kind: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class LootDrop(Base):
    """One item entry within a source's drop table."""

    __tablename__ = "loot_drops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("loot_sources.slug", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_low: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quantity_high: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    noted: Mapped[bool] = mapped_column(nullable=False, default=False)
    rarity_num: Mapped[int | None] = mapped_column(Integer)
    rarity_denom: Mapped[int | None] = mapped_column(Integer)
    rarity_text: Mapped[str | None] = mapped_column(Text)
    rolls: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    drop_group: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class EfficiencyRate(Base):
    """Ironman EHP (per-skill) or EHB (per-boss) rate from WiseOldMan."""

    __tablename__ = "efficiency_rates"
    __table_args__ = (
        UniqueConstraint("metric", "kind", name="uq_efficiency_metric_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
