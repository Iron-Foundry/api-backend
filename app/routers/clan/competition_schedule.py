"""Router for rolling competition schedule management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.competition_schedule import (
    CompetitionSchedule,
    ScheduledCompetitionRun,
)
from app.dependencies import get_session
from app.services.competition_schedule.repository import (
    create_run,
    get_active_run_for_schedule,
    get_all_schedules,
    get_run,
    get_runs_for_schedule,
    get_schedule,
    update_run,
    update_schedule,
)
from app.services.page_permissions import require_page_permission

router = APIRouter()

_READ_DEP = Depends(require_page_permission("staff.comp-schedule", "read"))
_WRITE_DEP = Depends(require_page_permission("staff.comp-schedule", "create"))


# ── Pydantic models ───────────────────────────────────────────────────────


class PollOptionBody(BaseModel):
    label: str = Field(min_length=1, max_length=55)
    metric: str = Field(min_length=1)


class CreateScheduleBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    poll_channel_id: str
    results_channel_id: str
    poll_duration_hours: float = Field(gt=0, le=72)
    competition_duration_hours: float = Field(gt=0, le=336)
    recurrence_days: float = Field(gt=0)
    poll_options: list[PollOptionBody] = Field(min_length=2, max_length=10)
    title_template: str = Field(default="{metric} Competition")
    next_poll_at: datetime


class PatchScheduleBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    poll_channel_id: str | None = None
    results_channel_id: str | None = None
    poll_duration_hours: float | None = Field(default=None, gt=0, le=72)
    competition_duration_hours: float | None = Field(default=None, gt=0, le=336)
    recurrence_days: float | None = Field(default=None, gt=0)
    poll_options: list[PollOptionBody] | None = None
    title_template: str | None = None
    next_poll_at: datetime | None = None
    is_active: bool | None = None


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _run_to_dict(run: ScheduledCompetitionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "schedule_id": run.schedule_id,
        "status": run.status,
        "poll_options_override": run.poll_options_override,
        "discord_poll_message_id": run.discord_poll_message_id,
        "discord_poll_channel_id": run.discord_poll_channel_id,
        "winning_metric": run.winning_metric,
        "wom_competition_id": run.wom_competition_id,
        "competition_title": run.competition_title,
        "poll_starts_at": run.poll_starts_at.isoformat()
        if run.poll_starts_at
        else None,
        "poll_ends_at": run.poll_ends_at.isoformat() if run.poll_ends_at else None,
        "competition_starts_at": run.competition_starts_at.isoformat()
        if run.competition_starts_at
        else None,
        "competition_ends_at": run.competition_ends_at.isoformat()
        if run.competition_ends_at
        else None,
        "error_detail": run.error_detail,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


async def _schedule_to_dict(
    sched: CompetitionSchedule, session: AsyncSession
) -> dict[str, Any]:
    active_run = await get_active_run_for_schedule(session, sched.id)
    return {
        "id": sched.id,
        "name": sched.name,
        "description": sched.description,
        "is_active": sched.is_active,
        "poll_channel_id": str(sched.poll_channel_id),
        "results_channel_id": str(sched.results_channel_id),
        "poll_duration_hours": sched.poll_duration_hours,
        "competition_duration_hours": sched.competition_duration_hours,
        "recurrence_days": sched.recurrence_days,
        "poll_options": sched.poll_options,
        "title_template": sched.title_template,
        "next_poll_at": sched.next_poll_at.isoformat() if sched.next_poll_at else None,
        "created_by": sched.created_by,
        "created_at": sched.created_at.isoformat(),
        "updated_at": sched.updated_at.isoformat(),
        "active_run": _run_to_dict(active_run) if active_run else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/competition-schedules", dependencies=[_READ_DEP])
async def list_schedules(session: AsyncSession = Depends(get_session)) -> list[dict]:
    schedules = await get_all_schedules(session)
    return [await _schedule_to_dict(s, session) for s in schedules]


@router.post("/competition-schedules", status_code=201, dependencies=[_WRITE_DEP])
async def create_schedule(
    body: CreateScheduleBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = _now()
    sched = CompetitionSchedule(
        name=body.name,
        description=body.description,
        is_active=True,
        poll_channel_id=int(body.poll_channel_id),
        results_channel_id=int(body.results_channel_id),
        poll_duration_hours=body.poll_duration_hours,
        competition_duration_hours=body.competition_duration_hours,
        recurrence_days=body.recurrence_days,
        poll_options=[o.model_dump() for o in body.poll_options],
        title_template=body.title_template,
        next_poll_at=body.next_poll_at,
        created_at=now,
        updated_at=now,
    )
    session.add(sched)
    await session.flush()
    await session.refresh(sched)
    result = await _schedule_to_dict(sched, session)
    await session.commit()
    return result


@router.get("/competition-schedules/{schedule_id}", dependencies=[_READ_DEP])
async def get_schedule_endpoint(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    return await _schedule_to_dict(sched, session)


@router.patch("/competition-schedules/{schedule_id}", dependencies=[_WRITE_DEP])
async def patch_schedule(
    schedule_id: int,
    body: PatchScheduleBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    patch = body.model_dump(exclude_none=True)
    if "poll_options" in patch:
        patch["poll_options"] = [
            o.model_dump() if hasattr(o, "model_dump") else o
            for o in patch["poll_options"]
        ]
    if "poll_channel_id" in patch:
        patch["poll_channel_id"] = int(patch["poll_channel_id"])
    if "results_channel_id" in patch:
        patch["results_channel_id"] = int(patch["results_channel_id"])
    await update_schedule(session, sched, **patch)
    result = await _schedule_to_dict(sched, session)
    await session.commit()
    return result


@router.delete(
    "/competition-schedules/{schedule_id}", status_code=204, dependencies=[_WRITE_DEP]
)
async def delete_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    await session.delete(sched)
    await session.commit()


@router.post("/competition-schedules/{schedule_id}/pause", dependencies=[_WRITE_DEP])
async def pause_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    await update_schedule(session, sched, is_active=False)
    result = await _schedule_to_dict(sched, session)
    await session.commit()
    return result


@router.post("/competition-schedules/{schedule_id}/resume", dependencies=[_WRITE_DEP])
async def resume_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    await update_schedule(session, sched, is_active=True)
    result = await _schedule_to_dict(sched, session)
    await session.commit()
    return result


@router.post(
    "/competition-schedules/{schedule_id}/skip-next", dependencies=[_WRITE_DEP]
)
async def skip_next(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")

    active_run = await get_active_run_for_schedule(session, schedule_id)
    if active_run:
        await update_run(session, active_run, status="skipped")

    from datetime import timedelta

    now = _now()
    next_poll = now + timedelta(days=sched.recurrence_days)
    await update_schedule(session, sched, next_poll_at=next_poll)
    await session.commit()
    return {"skipped": True, "next_poll_at": next_poll.isoformat()}


@router.post(
    "/competition-schedules/{schedule_id}/trigger-now", dependencies=[_WRITE_DEP]
)
async def trigger_now(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    active_run = await get_active_run_for_schedule(session, schedule_id)
    if active_run and active_run.status in ("pending_poll", "poll_active"):
        raise HTTPException(
            409,
            f"A poll is already running for this schedule (run id={active_run.id}, status={active_run.status}). Use skip-next first.",
        )
    from datetime import timedelta

    # Set slightly in the past so the tick always evaluates it as due
    past = _now() - timedelta(seconds=5)
    await update_schedule(session, sched, next_poll_at=past)
    await session.commit()
    return {"triggered": True, "next_poll_at": past.isoformat()}


@router.patch(
    "/competition-schedules/{schedule_id}/next-poll-at", dependencies=[_WRITE_DEP]
)
async def set_next_poll_at(
    schedule_id: int,
    body: dict,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    next_poll_at = body.get("next_poll_at")
    if not next_poll_at:
        raise HTTPException(422, "next_poll_at required")
    if isinstance(next_poll_at, str):
        next_poll_at = datetime.fromisoformat(next_poll_at)
    await update_schedule(session, sched, next_poll_at=next_poll_at)
    result = await _schedule_to_dict(sched, session)
    await session.commit()
    return result


class OverrideOptionsBody(BaseModel):
    options: list[PollOptionBody] = Field(min_length=2, max_length=10)
    run_id: int | None = None


@router.post(
    "/competition-schedules/{schedule_id}/override-options", dependencies=[_WRITE_DEP]
)
async def override_options(
    schedule_id: int,
    body: OverrideOptionsBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")

    options = [o.model_dump() for o in body.options]

    if body.run_id:
        run = await get_run(session, body.run_id)
        if not run or run.schedule_id != schedule_id:
            raise HTTPException(404, "Run not found")
        await update_run(session, run, poll_options_override=options)
        await session.commit()
        return _run_to_dict(run)

    # Find existing pending_poll run or create one + trigger now
    active_run = await get_active_run_for_schedule(session, schedule_id)
    if active_run and active_run.status == "pending_poll":
        await update_run(session, active_run, poll_options_override=options)
        await session.commit()
        return _run_to_dict(active_run)

    now = _now()
    run = await create_run(session, schedule_id, poll_options_override=options)
    await update_schedule(session, sched, next_poll_at=now)
    await session.commit()
    return _run_to_dict(run)


class PatchRunBody(BaseModel):
    status: str | None = None
    winning_metric: str | None = None
    wom_competition_id: int | None = None
    competition_title: str | None = None
    competition_starts_at: datetime | None = None
    competition_ends_at: datetime | None = None
    error_detail: str | None = None


@router.patch(
    "/competition-schedules/{schedule_id}/runs/{run_id}", dependencies=[_WRITE_DEP]
)
async def patch_run(
    schedule_id: int,
    run_id: int,
    body: PatchRunBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    run = await get_run(session, run_id)
    if not run or run.schedule_id != schedule_id:
        raise HTTPException(404, "Run not found")
    patch = body.model_dump(exclude_none=True)
    effective_ends_at = patch.get("competition_ends_at") or run.competition_ends_at
    effective_status = patch.get("status") or run.status
    if (
        effective_status == "competition_active"
        and effective_ends_at
        and effective_ends_at <= _now()
    ):
        raise HTTPException(
            422,
            f"competition_ends_at {effective_ends_at.isoformat()} is already in the past - "
            "the tick would announce results immediately. Use a future time (UTC).",
        )
    if patch:
        await update_run(session, run, **patch)
    await session.commit()
    return _run_to_dict(run)


@router.get("/competition-schedules/{schedule_id}/runs", dependencies=[_READ_DEP])
async def list_runs(
    schedule_id: int,
    status: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    sched = await get_schedule(session, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")
    runs = await get_runs_for_schedule(session, schedule_id, status=status, limit=limit)
    return [_run_to_dict(r) for r in runs]
