"""SQLAlchemy ORM models — canonical PostgreSQL schema definition.

These classes mirror the tables created by the Alembic migrations and act as
the single source of truth for alembic autogenerate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Integer, Text, ARRAY, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    discord_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_username: Mapped[str] = mapped_column(Text, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    rsn: Mapped[str | None] = mapped_column(Text, unique=True)
    clan_rank: Mapped[str | None] = mapped_column(Text)
    discord_roles: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    ticket_ids: Mapped[list] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{}"
    )
    total_loot_value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    clan_donated: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    collection_log_slots: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    collection_log_slots_max: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    stats_opt_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    hide_presence_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    recruited_by: Mapped[int | None] = mapped_column(BigInteger)
    api_key: Mapped[str | None] = mapped_column(Text, unique=True)
    key_is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    key_created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    key_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    temp_vc_lock_status: Mapped[str | None] = mapped_column(Text)
    temp_vc_member_limit: Mapped[int | None] = mapped_column(Integer)
    temp_vc_bitrate: Mapped[int | None] = mapped_column(Integer)
    join_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str | None] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    raw_message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)


class CofferEvent(Base):
    __tablename__ = "coffer_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    raw_message: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_donation: Mapped[bool] = mapped_column(Boolean, nullable=False)


class MembershipEvent(Base):
    __tablename__ = "membership_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    player_name: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    is_league_world: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    raw_message: Mapped[str | None] = mapped_column(Text)
    expelled_by: Mapped[str | None] = mapped_column(Text)


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


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ticket_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_staff: Mapped[list] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default="{}"
    )
    participants: Mapped[list] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default="{}"
    )
    closed_by_id: Mapped[int | None] = mapped_column(BigInteger)
    first_staff_response_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    panel_message_id: Mapped[int | None] = mapped_column(BigInteger)
    staff_note: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)
    reopen_history: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    timeout_frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    extra_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}", name="metadata")


class Transcript(Base):
    __tablename__ = "transcripts"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")


class SurveyTemplate(Base):
    __tablename__ = "survey_templates"

    template_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SurveyActive(Base):
    __tablename__ = "survey_active"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    responses: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Config(Base):
    __tablename__ = "config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class RolePanel(Base):
    __tablename__ = "role_panels"

    panel_id: Mapped[str] = mapped_column(Text, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    max_selectable: Mapped[int | None] = mapped_column(Integer)
    roles: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
