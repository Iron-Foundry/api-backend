from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Float,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SourceKillRate(Base):
    """A staff-set kill rate for an OSRSClans drop source that has none.

    `source` is the OSRSClans source key, such as `Herbiboar`.
    """

    __tablename__ = "source_kill_rates"
    __table_args__ = (
        CheckConstraint("kills_per_hour > 0", name="ck_source_kill_rate_positive"),
    )

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    kills_per_hour: Mapped[float] = mapped_column(Float, nullable=False)
    set_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
