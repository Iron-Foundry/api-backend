"""DB helpers for competition schedule state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.competition_schedule import (
    CompetitionSchedule,
    ScheduledCompetitionRun,
)

_ACTIVE_STATUSES = {
    "pending_poll",
    "poll_active",
    "competition_pending",
    "competition_active",
}
_TERMINAL_STATUSES = {"results_announced", "skipped", "error"}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def get_active_schedules(session: AsyncSession) -> Sequence[CompetitionSchedule]:
    result = await session.execute(
        select(CompetitionSchedule).where(CompetitionSchedule.is_active == True)  # noqa: E712
    )
    return result.scalars().all()


async def get_all_schedules(session: AsyncSession) -> Sequence[CompetitionSchedule]:
    result = await session.execute(
        select(CompetitionSchedule).order_by(CompetitionSchedule.id)
    )
    return result.scalars().all()


async def get_schedule(
    session: AsyncSession, schedule_id: int
) -> CompetitionSchedule | None:
    result = await session.execute(
        select(CompetitionSchedule).where(CompetitionSchedule.id == schedule_id)
    )
    return result.scalar_one_or_none()


async def get_runs_in_statuses(
    session: AsyncSession, statuses: list[str]
) -> Sequence[ScheduledCompetitionRun]:
    result = await session.execute(
        select(ScheduledCompetitionRun).where(
            ScheduledCompetitionRun.status.in_(statuses)
        )
    )
    return result.scalars().all()


async def get_active_run_for_schedule(
    session: AsyncSession, schedule_id: int
) -> ScheduledCompetitionRun | None:
    result = await session.execute(
        select(ScheduledCompetitionRun).where(
            ScheduledCompetitionRun.schedule_id == schedule_id,
            ScheduledCompetitionRun.status.in_(list(_ACTIVE_STATUSES)),
        )
    )
    return result.scalar_one_or_none()


async def get_runs_for_schedule(
    session: AsyncSession,
    schedule_id: int,
    *,
    status: str | None = None,
    limit: int = 20,
) -> Sequence[ScheduledCompetitionRun]:
    q = select(ScheduledCompetitionRun).where(
        ScheduledCompetitionRun.schedule_id == schedule_id
    )
    if status:
        q = q.where(ScheduledCompetitionRun.status == status)
    q = q.order_by(ScheduledCompetitionRun.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


async def get_run(session: AsyncSession, run_id: int) -> ScheduledCompetitionRun | None:
    result = await session.execute(
        select(ScheduledCompetitionRun).where(ScheduledCompetitionRun.id == run_id)
    )
    return result.scalar_one_or_none()


async def create_run(
    session: AsyncSession,
    schedule_id: int,
    *,
    poll_options_override: list | None = None,
) -> ScheduledCompetitionRun:
    now = _now()
    run = ScheduledCompetitionRun(
        schedule_id=schedule_id,
        status="pending_poll",
        poll_options_override=poll_options_override,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def update_run(
    session: AsyncSession, run: ScheduledCompetitionRun, **kwargs: object
) -> ScheduledCompetitionRun:
    for key, value in kwargs.items():
        setattr(run, key, value)
    run.updated_at = _now()
    await session.flush()
    return run


async def update_schedule(
    session: AsyncSession, schedule: CompetitionSchedule, **kwargs: object
) -> CompetitionSchedule:
    for key, value in kwargs.items():
        setattr(schedule, key, value)
    schedule.updated_at = _now()
    await session.flush()
    return schedule
