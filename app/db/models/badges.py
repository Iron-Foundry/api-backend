from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Text
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
