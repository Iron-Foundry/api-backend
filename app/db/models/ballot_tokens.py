from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BallotTokenAccount(Base):
    __tablename__ = "ballot_token_accounts"

    discord_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.discord_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class BallotTokenTransaction(Base):
    __tablename__ = "ballot_token_transactions"
    __table_args__ = (Index("ix_ballot_token_transactions_user", "discord_user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scheduled_competition_runs.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class BallotPollVote(Base):
    __tablename__ = "ballot_poll_votes"
    __table_args__ = (
        UniqueConstraint("run_id", "discord_user_id", name="uq_ballot_vote_once"),
        Index("ix_ballot_poll_votes_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scheduled_competition_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
