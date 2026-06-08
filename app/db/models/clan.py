from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, BigInteger, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
