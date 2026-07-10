from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, LargeBinary, SmallInteger, String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MapTile(Base):
    __tablename__ = "map_tiles"

    plane: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    z: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    dominant_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    has_content: Mapped[bool] = mapped_column(Boolean, nullable=False)
    region_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
