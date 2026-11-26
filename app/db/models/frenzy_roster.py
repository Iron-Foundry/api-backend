from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FrenzyTeam(Base):
    __tablename__ = "frenzy_teams"
    __table_args__ = (UniqueConstraint("event_id", "slug", name="uq_frenzy_team_slug"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    participants: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    item_progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    activity_progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    milestone_progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FrenzySignup(Base):
    """A member's signup for a frenzy event, under one of their linked RSNs."""

    __tablename__ = "frenzy_signups"
    __table_args__ = (
        UniqueConstraint("event_id", "discord_user_id", name="uq_frenzy_signup"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id", ondelete="SET NULL")
    )
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text)
    wants_captain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("frenzy_teams.id", ondelete="SET NULL"), index=True
    )
    pick_number: Mapped[int | None] = mapped_column(Integer)
    pick_kind: Mapped[str | None] = mapped_column(Text)
    signed_up_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FrenzyDraft(Base):
    """The captain draft of one frenzy event: its mode, its drawn order and its turn."""

    __tablename__ = "frenzy_drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    top_picks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    captain_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    team_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    next_pick: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
