from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FrenzyTemplate(Base):
    __tablename__ = "frenzy_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tiers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    activities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    milestones: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    multipliers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class FrenzyTemplateVersion(Base):
    __tablename__ = "frenzy_template_versions"
    __table_args__ = (
        Index("ix_frenzy_template_versions_lookup", "template_id", "version_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tiers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    activities: Mapped[list] = mapped_column(JSONB, nullable=False)
    milestones: Mapped[dict] = mapped_column(JSONB, nullable=False)
    multipliers: Mapped[list] = mapped_column(JSONB, nullable=False)
    edited_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class FrenzyEvent(Base):
    __tablename__ = "frenzy_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("frenzy_templates.id"), nullable=False)
    wom_comp_id: Mapped[int | None] = mapped_column(Integer)
    leaderboard_metrics: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    trusted_sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    starts_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


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
    participants: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    item_progress: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    activity_progress: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    milestone_progress: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class FrenzySubmission(Base):
    __tablename__ = "frenzy_submissions"
    __table_args__ = (
        Index("ix_frenzy_submissions_team_status", "team_id", "status"),
        Index("ix_frenzy_submissions_event_status", "event_id", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_rsn: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    submission_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    auto_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
