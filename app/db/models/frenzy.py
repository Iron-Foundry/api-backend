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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FrenzyTemplate(Base):
    __tablename__ = "frenzy_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tiers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    activities: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    milestones: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    multipliers: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    total_point_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


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
    tiers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    activities: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    milestones: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    multipliers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    edited_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FrenzyEvent(Base):
    __tablename__ = "frenzy_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frenzy_templates.id"), nullable=False
    )
    wom_comp_id: Mapped[int | None] = mapped_column(Integer)
    leaderboard_metrics: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    trusted_sources: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    starts_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    signups_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
