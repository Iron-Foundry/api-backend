"""SQLAlchemy ORM models - canonical PostgreSQL schema definition.

These classes mirror the tables created by the Alembic migrations and act as
the single source of truth for alembic autogenerate.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
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
    referral_source: Mapped[str | None] = mapped_column(Text)
    referral_detail: Mapped[str | None] = mapped_column(Text)
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


class UserAccount(Base):
    """One row per RSN linked to a Discord user. Replaces the single users.rsn field."""

    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.discord_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
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
    notification_category_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    hub_code: Mapped[str] = mapped_column(Text, nullable=False)
    discord_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    members: Mapped[list[PartyMemberDB]] = relationship(
        "PartyMemberDB",
        back_populates="party",
        cascade="all, delete-orphan",
        order_by="PartyMemberDB.joined_at",
    )


class PartyMemberDB(Base):
    __tablename__ = "party_members"
    __table_args__ = (UniqueConstraint("party_id", "user_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    party_id: Mapped[str] = mapped_column(
        Text, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    rsn: Mapped[str | None] = mapped_column(Text)
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    party: Mapped[PartyDB] = relationship("PartyDB", back_populates="members")


class PartyChatMessageDB(Base):
    __tablename__ = "party_chat_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    party_id: Mapped[str] = mapped_column(
        Text, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    rsn: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class PartyNotificationPreferences(Base):
    __tablename__ = "party_notification_preferences"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )


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


class FrenzyTemplate(Base):
    __tablename__ = "frenzy_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tiers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    activities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    milestones: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    multipliers: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
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
    tiers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    activities: Mapped[list] = mapped_column(JSONB, nullable=False)
    milestones: Mapped[dict] = mapped_column(JSONB, nullable=False)
    multipliers: Mapped[list] = mapped_column(JSONB, nullable=False)
    edited_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FrenzyEvent(Base):
    __tablename__ = "frenzy_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("frenzy_templates.id"),
        nullable=False,
    )
    wom_comp_id: Mapped[int | None] = mapped_column(Integer)
    leaderboard_metrics: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    trusted_sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    starts_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


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
    participants: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    item_progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    activity_progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    milestone_progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FrenzySubmission(Base):
    __tablename__ = "frenzy_submissions"
    __table_args__ = (
        Index("ix_frenzy_submissions_team_status", "team_id", "status"),
        Index(
            "ix_frenzy_submissions_event_status", "event_id", "status", "submitted_at"
        ),
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
    auto_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_type_status", "type", "status"),
        Index("ix_feedback_discord_user", "discord_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # suggestion | bug
    type: Mapped[str] = mapped_column(Text, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # { steps_to_reproduce } for bugs; {} for suggestions
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # open | in-review | implemented | wont-fix | solved | closed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    # list of Asset UUIDs (as strings)
    attachment_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FeedbackReaction(Base):
    __tablename__ = "feedback_reactions"

    feedback_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    discord_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class FeedbackReply(Base):
    __tablename__ = "feedback_replies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class ServiceStatus(Base):
    """Live health snapshot for each reporting service. Upserted on every report."""

    __tablename__ = "service_status"

    service_name: Mapped[str] = mapped_column(Text, primary_key=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    version: Mapped[str | None] = mapped_column(Text)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    summary_metrics: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class MetricRecord(Base):
    """Raw time-series metric record. Kept for 3 months, then compacted."""

    __tablename__ = "metric_records"
    __table_args__ = (
        Index("ix_metric_records_lookup", "service_name", "module_name", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class MetricRecordCompact(Base):
    """Daily aggregate of metric_records older than 3 months."""

    __tablename__ = "metric_records_compact"
    __table_args__ = (
        UniqueConstraint(
            "service_name", "module_name", "date", name="uq_metric_compact_day"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_agg: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
