from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
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
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    requirement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
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
    signups_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    fog_of_war: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_finished: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    rolls_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    winner_team_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_category_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_captains_role_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_captains_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    grid_cols: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    grid_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    dice_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    dice_sides: Mapped[int] = mapped_column(Integer, nullable=False, server_default="6")
    team_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    background_url: Mapped[str | None] = mapped_column(Text)
    cells: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    start_pad: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    end_pad: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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
    discord_role_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_text_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_voice_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    pending_effects: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceRoll(Base):
    __tablename__ = "tilerace_rolls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    dice: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default="[]")
    roll: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    new_position: Mapped[int] = mapped_column(Integer, nullable=False)
    rolled_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rolled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceCompletion(Base):
    __tablename__ = "tilerace_tile_completions"
    __table_args__ = (
        UniqueConstraint("team_id", "path_position", name="uq_tilerace_completion"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    path_position: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_by: Mapped[int | None] = mapped_column(BigInteger)
    completed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class TileRaceSignup(Base):
    __tablename__ = "tilerace_signups"
    __table_args__ = (
        UniqueConstraint("event_id", "discord_user_id", name="uq_tilerace_signup"),
        Index(
            "uq_tilerace_team_captain",
            "team_id",
            unique=True,
            postgresql_where=text("is_captain AND team_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tilerace_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tilerace_teams.id", ondelete="SET NULL")
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id", ondelete="SET NULL")
    )
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    ranking_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    wants_captain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_captain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    added_by_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
