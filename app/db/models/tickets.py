from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
