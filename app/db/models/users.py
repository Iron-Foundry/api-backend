from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
    rsn_history: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
