from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Text, TIMESTAMP
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RuneLiteConfig(Base):
    """A stored RuneLite config object shared across the site.

    The `type` column discriminates object kinds (first supported: tile_marker).
    The `data` column holds the RuneLite export verbatim so it round-trips
    losslessly for downstream rendering and re-import.
    """

    __tablename__ = "runelite_configs"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    data: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
