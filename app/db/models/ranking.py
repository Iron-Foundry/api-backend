from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PlayerRanking(Base):
    __tablename__ = "player_rankings"
    __table_args__ = (UniqueConstraint("rsn", name="uq_player_rankings_rsn"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    boss_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    skill_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class PlayerSnapshot(Base):
    __tablename__ = "player_snapshots"
    __table_args__ = (UniqueConstraint("rsn", name="uq_player_snapshots_rsn"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    bosses: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    activities: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class CompetitionSnapshot(Base):
    """Periodic snapshot of top-5 competition progress. One row per (comp_id, metric, poll)."""

    __tablename__ = "competition_snapshots"
    __table_args__ = (
        Index("ix_competition_snapshots_lookup", "comp_id", "metric", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comp_id: Mapped[int] = mapped_column(Integer, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    series: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
