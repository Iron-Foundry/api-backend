from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CompetitionSchedule(Base):
    __tablename__ = "competition_schedules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    poll_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    results_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    poll_duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    competition_duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    recurrence_days: Mapped[float] = mapped_column(Float, nullable=False)
    poll_options: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    title_template: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="{metric} Competition"
    )
    next_poll_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    runs: Mapped[list[ScheduledCompetitionRun]] = relationship(
        "ScheduledCompetitionRun",
        back_populates="schedule",
        cascade="all, delete-orphan",
    )


class ScheduledCompetitionRun(Base):
    __tablename__ = "scheduled_competition_runs"
    __table_args__ = (
        Index("ix_scheduled_competition_runs_schedule_status", "schedule_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("competition_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending_poll"
    )
    poll_options_override: Mapped[list | None] = mapped_column(JSONB)
    discord_poll_message_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_poll_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    winning_metric: Mapped[str | None] = mapped_column(Text)
    wom_competition_id: Mapped[int | None] = mapped_column(Integer)
    competition_title: Mapped[str | None] = mapped_column(Text)
    poll_starts_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    poll_ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    competition_starts_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    competition_ends_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    schedule: Mapped[CompetitionSchedule] = relationship(
        "CompetitionSchedule", back_populates="runs"
    )
