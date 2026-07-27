"""Ballot token config resolution and capped award/refund helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ballot_tokens import (
    BallotPollVote,
    BallotTokenAccount,
    BallotTokenTransaction,
)
from app.db.models.competition_schedule import (
    CompetitionSchedule,
    ScheduledCompetitionRun,
)
from app.db.models.config import Config

BALLOT_TOKEN_CONFIG_KEY = "ballot_token_config"
_GLOBAL_GUILD_ID = 0

DEFAULT_TOKEN_CONFIG: dict[str, Any] = {
    "placement_tokens": [10, 7, 5, 3, 2],
    "bonus_threshold_pct": 10,
    "bonus_tokens": 1,
    "vote_cost": 1,
    "max_hold": 100,
}


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def resolve_token_config(
    session: AsyncSession, schedule: CompetitionSchedule | None
) -> dict[str, Any]:
    """Merge global ballot token config over defaults, then per-schedule override."""
    merged = dict(DEFAULT_TOKEN_CONFIG)
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _GLOBAL_GUILD_ID,
            Config.key == BALLOT_TOKEN_CONFIG_KEY,
        )
    )
    stored = result.scalar_one_or_none() or {}
    merged.update({k: v for k, v in stored.items() if k in DEFAULT_TOKEN_CONFIG})
    override = schedule.token_config_override if schedule else None
    if override:
        merged.update({k: v for k, v in override.items() if k in DEFAULT_TOKEN_CONFIG})
    return merged


async def _apply_capped_delta(
    session: AsyncSession, discord_user_id: int, delta: int, max_hold: int
) -> int:
    now = _now()
    existing = await session.execute(
        select(BallotTokenAccount.balance).where(
            BallotTokenAccount.discord_user_id == discord_user_id
        )
    )
    old_balance = existing.scalar_one_or_none() or 0
    result = await session.execute(
        pg_insert(BallotTokenAccount)
        .values(
            discord_user_id=discord_user_id,
            balance=min(delta, max_hold),
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["discord_user_id"],
            set_={
                "balance": func.least(BallotTokenAccount.balance + delta, max_hold),
                "updated_at": now,
            },
        )
        .returning(BallotTokenAccount.balance)
    )
    new_balance = result.scalar_one()
    return new_balance - old_balance


async def _record(
    session: AsyncSession,
    discord_user_id: int,
    delta: int,
    reason: str,
    run_id: int | None,
) -> None:
    session.add(
        BallotTokenTransaction(
            discord_user_id=discord_user_id,
            delta=delta,
            reason=reason,
            run_id=run_id,
            created_at=_now(),
        )
    )


async def award_tokens(
    session: AsyncSession,
    awards: list[tuple[int, int, str]],
    run_id: int,
    max_hold: int,
) -> None:
    """Apply (discord_user_id, amount, reason) awards, capped at max_hold."""
    for discord_user_id, amount, reason in awards:
        if amount <= 0:
            continue
        effective = await _apply_capped_delta(
            session, discord_user_id, amount, max_hold
        )
        if effective != 0:
            await _record(session, discord_user_id, effective, reason, run_id)


async def refund_run_votes(
    session: AsyncSession, run_id: int, vote_cost: int, max_hold: int
) -> int:
    """Credit vote_cost back to every voter of a run. Returns count refunded."""
    voters = await session.execute(
        select(BallotPollVote.discord_user_id).where(BallotPollVote.run_id == run_id)
    )
    ids = [row[0] for row in voters.all()]
    for discord_user_id in ids:
        effective = await _apply_capped_delta(
            session, discord_user_id, vote_cost, max_hold
        )
        if effective != 0:
            await _record(session, discord_user_id, effective, "refund", run_id)
    return len(ids)


async def refund_run(
    session: AsyncSession,
    run: ScheduledCompetitionRun,
    schedule: CompetitionSchedule | None,
) -> int:
    """Refund every voter of a run once, guarded by votes_refunded_at."""
    if run.votes_refunded_at is not None:
        return 0
    config = await resolve_token_config(session, schedule)
    refunded = await refund_run_votes(
        session, run.id, config["vote_cost"], config["max_hold"]
    )
    run.votes_refunded_at = _now()
    run.updated_at = _now()
    return refunded
