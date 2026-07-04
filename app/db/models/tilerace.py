from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TileRepositoryTile(Base):
    __tablename__ = "tile_repository_tiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    icon_url: Mapped[str | None] = mapped_column(Text)
    icon_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="wiki"
    )
    items: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceEvent(Base):
    __tablename__ = "tilerace_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    fog_of_war: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    grid_cols: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    grid_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    background_url: Mapped[str | None] = mapped_column(Text)
    cells: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    starts_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceTeam(Base):
    __tablename__ = "tilerace_teams"
    __table_args__ = (
        UniqueConstraint("event_id", "slug", name="uq_tilerace_team_slug"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    icon_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="item")
    icon_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    color: Mapped[str] = mapped_column(Text, nullable=False, server_default="#888888")
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    members: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceSignup(Base):
    __tablename__ = "tilerace_signups"
    __table_args__ = (
        UniqueConstraint("event_id", "discord_user_id", name="uq_tilerace_signup"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    ranking_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
