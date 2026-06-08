from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, Index, Integer, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ServiceStatus(Base):
    """Live health snapshot for each reporting service. Upserted on every report."""

    __tablename__ = "service_status"

    service_name: Mapped[str] = mapped_column(Text, primary_key=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[str | None] = mapped_column(Text)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    summary_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class MetricRecord(Base):
    """Raw time-series metric record. Kept for 3 months, then compacted."""

    __tablename__ = "metric_records"
    __table_args__ = (
        Index("ix_metric_records_lookup", "service_name", "module_name", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class MetricRecordCompact(Base):
    """Daily aggregate of metric_records older than 3 months."""

    __tablename__ = "metric_records_compact"
    __table_args__ = (
        UniqueConstraint("service_name", "module_name", "date", name="uq_metric_compact_day"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_agg: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
