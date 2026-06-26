from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Text, TIMESTAMP, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MemberGoals(Base):
    __tablename__ = "member_goals"
    __table_args__ = (UniqueConstraint("discord_user_id", "rsn", name="uq_member_goals_user_rsn"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rsn: Mapped[str] = mapped_column(Text, nullable=False)
    goals: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    share_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
