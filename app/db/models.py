"""SQLAlchemy ORM models — canonical PostgreSQL schema definition.

These classes mirror the tables created by the Alembic migrations and act as
the single source of truth for alembic autogenerate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    ARRAY,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    discord_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_username: Mapped[str] = mapped_column(Text, nullable=False)
    discord_avatar_url: Mapped[str | None] = mapped_column(Text)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
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
    roles_fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class ClanStats(Base):
    """Single-row table holding the latest WOM clan stat snapshot. Always id=1."""

    __tablename__ = "clan_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_count: Mapped[int | None] = mapped_column(Integer)
    total_xp: Mapped[int | None] = mapped_column(BigInteger)
    total_ehb: Mapped[int | None] = mapped_column(Integer)
    cox_kc: Mapped[int | None] = mapped_column(Integer)
    tob_kc: Mapped[int | None] = mapped_column(Integer)
    toa_kc: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class PartyDB(Base):
    __tablename__ = "parties"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    leader_id: Mapped[str] = mapped_column(Text, nullable=False)
    leader_username: Mapped[str] = mapped_column(Text, nullable=False)
    leader_rsn: Mapped[str | None] = mapped_column(Text)
    activity: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    vibe: Mapped[str] = mapped_column(Text, nullable=False, server_default="chill")
    max_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ping_role_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    hub_code: Mapped[str] = mapped_column(Text, nullable=False)
    discord_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    members: Mapped[list[PartyMemberDB]] = relationship(
        "PartyMemberDB", back_populates="party", cascade="all, delete-orphan",
        order_by="PartyMemberDB.joined_at",
    )


class PartyMemberDB(Base):
    __tablename__ = "party_members"
    __table_args__ = (UniqueConstraint("party_id", "user_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    party_id: Mapped[str] = mapped_column(Text, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    rsn: Mapped[str | None] = mapped_column(Text)
    joined_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    party: Mapped[PartyDB] = relationship("PartyDB", back_populates="members")


class PartyChatMessageDB(Base):
    __tablename__ = "party_chat_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    party_id: Mapped[str] = mapped_column(Text, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    rsn: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
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
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
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
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
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

    ticket_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ticket_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
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
    extra_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", name="metadata"
    )


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


class WebSurveySubmission(Base):
    __tablename__ = "web_survey_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Config(Base):
    __tablename__ = "config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    icon: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(Text, nullable=False, server_default="'#6366f1'")
    text_color: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="'#ffffff'"
    )
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger)


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    badge_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("badges.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    assigned_by: Mapped[int | None] = mapped_column(BigInteger)


class ContentCategory(Base):
    __tablename__ = "content_categories"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_type: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("content_categories.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger)


class ContentEntry(Base):
    __tablename__ = "content_entries"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("content_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deprecated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deprecated_by: Mapped[int | None] = mapped_column(BigInteger)


class ContentCollaborator(Base):
    __tablename__ = "content_collaborators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("content_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    added_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ContentEntryVersion(Base):
    __tablename__ = "content_entry_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("content_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


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
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class ContentEntryReaction(Base):
    __tablename__ = "content_entry_reactions"
    __table_args__ = (
        UniqueConstraint(
            "entry_id", "discord_user_id", name="uq_content_entry_reaction"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("content_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
