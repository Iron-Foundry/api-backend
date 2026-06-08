from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str | None] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw_message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class CofferEvent(Base):
    __tablename__ = "coffer_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw_message: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_donation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class MembershipEvent(Base):
    __tablename__ = "membership_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw_message: Mapped[str | None] = mapped_column(Text)
    expelled_by: Mapped[str | None] = mapped_column(Text)
    user_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class Leaderboard(Base):
    __tablename__ = "leaderboards"

    player_name: Mapped[str] = mapped_column(Text, primary_key=True)
    activity: Mapped[str] = mapped_column(Text, primary_key=True)
    variant: Mapped[str] = mapped_column(Text, primary_key=True, server_default="")
    time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int | None] = mapped_column(Integer)
    total_value: Mapped[int | None] = mapped_column(BigInteger)
    achieved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_updated: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
