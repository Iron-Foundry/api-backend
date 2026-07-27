from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Integer, Text
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


class WomClanRank(Base):
    """WOM clan rank for every member, keyed by lowercase RSN.

    Populated by the hourly WOM sync and used as a fallback rank source
    for leaderboard entries where the player has no linked Discord account.
    """

    __tablename__ = "wom_clan_ranks"

    rsn: Mapped[str] = mapped_column(Text, primary_key=True)
    clan_rank: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
