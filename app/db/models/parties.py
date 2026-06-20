from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


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
