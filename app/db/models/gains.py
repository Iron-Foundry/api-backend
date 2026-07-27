from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BulkGainsBatch(Base):
    """One row per bulk-gained fetch operation."""

    __tablename__ = "bulk_gains_batches"
    __table_args__ = (Index("ix_bulk_gains_batches_captured_at", "captured_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    period: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class PlayerBulkGains(Base):
    """Per-player gains snapshot from a bulk-gained fetch. One row per player per batch."""

    __tablename__ = "player_bulk_gains"
    __table_args__ = (
        Index("ix_player_bulk_gains_batch_id", "batch_id"),
        Index("ix_player_bulk_gains_rsn_range", "rsn", "gains_start", "gains_end"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    gains_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    gains_end: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    skills: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    bosses: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    activities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
