"""Background service driving the rolling competition schedule state machine."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from loguru import logger
from valkey.asyncio import Valkey

from app.services.competitions import CreateCompetitionInput, create_competition
from app.services.http import WiseOldManHandler, WomPriority
from .repository import (
    create_run,
    get_active_run_for_schedule,
    get_active_schedules,
    get_run,
    get_runs_in_statuses,
    update_run,
    update_schedule,
)

_TICK_INTERVAL = 60  # seconds
_POLL_ACK_GRACE = 120  # seconds before republishing unacknowledged poll
_VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")

_CH_CREATE_POLL = "foundry:comp_schedule:create_poll"
_CH_POLL_POSTED = "foundry:comp_schedule:poll_posted"
_CH_POLL_RESULT = "foundry:comp_schedule:poll_result"
_CH_CLOSE_POLL = "foundry:comp_schedule:close_poll"
_CH_ANNOUNCE = "foundry:comp_schedule:announce_results"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class CompetitionScheduleService:
    """Drives the rolling competition schedule: polls -> WOM comps -> announcements."""

    def __init__(
        self,
        session_factory,  # type: ignore[no-untyped-def]
        valkey: Valkey,
        group_id: int,
        group_key: str,
        api_key: str | None = None,
        discord_contact: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._valkey = valkey
        self._group_id = group_id
        self._group_key = group_key
        self._api_key = api_key
        self._discord_contact = discord_contact
        self._tick_task: asyncio.Task[None] | None = None
        self._sub_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._tick_task is not None and not self._tick_task.done()

    async def start(self) -> None:
        self._tick_task = asyncio.create_task(
            self._tick_loop(), name="comp-schedule-tick"
        )
        self._sub_task = asyncio.create_task(
            self._subscriber_loop(), name="comp-schedule-sub"
        )
        logger.info("CompetitionScheduleService started")

    async def stop(self) -> None:
        for task in (self._tick_task, self._sub_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("CompetitionScheduleService stopped")

    # ── Tick loop ─────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                logger.warning("CompetitionScheduleService tick error: {}", exc)
            await asyncio.sleep(_TICK_INTERVAL)

    async def _tick(self) -> None:
        if not self._session_factory:
            return
        async with self._session_factory() as session:
            now = _now()

            # Fire polls for schedules whose next_poll_at has passed
            schedules = await get_active_schedules(session)
            for sched in schedules:
                if sched.next_poll_at is None or sched.next_poll_at > now:
                    continue
                existing = await get_active_run_for_schedule(session, sched.id)
                if existing is None:
                    await self._fire_poll(session, sched, now)
                elif (
                    existing.status == "pending_poll"
                    and existing.poll_starts_at is None
                ):
                    # Stuck pending_poll (fire_poll crashed before publish) - retry
                    await self._fire_existing_run(session, sched, existing, now)

            # Republish create_poll for poll_active runs not yet acknowledged by bot;
            # signal close for overdue polls whose Discord message is known
            poll_active = await get_runs_in_statuses(session, ["poll_active"])
            for run in poll_active:
                if (
                    run.discord_poll_message_id is None
                    and run.poll_starts_at is not None
                    and (now - run.poll_starts_at).total_seconds() > _POLL_ACK_GRACE
                ):
                    await self._republish_poll(session, run)
                elif (
                    run.discord_poll_message_id is not None
                    and run.poll_ends_at is not None
                    and run.poll_ends_at <= now
                ):
                    await self._request_poll_close(session, run)

            # Handle competition_pending: create WOM competition
            pending = await get_runs_in_statuses(session, ["competition_pending"])
            for run in pending:
                await self._create_wom_competition(session, run)

            # Handle competition_active: check if ended, announce
            active = await get_runs_in_statuses(session, ["competition_active"])
            for run in active:
                if run.competition_ends_at and run.competition_ends_at <= now:
                    await self._announce_results(session, run)

            await session.commit()

    async def _build_poll_payload(self, run, sched) -> str:  # type: ignore[no-untyped-def]
        effective_options = run.poll_options_override or sched.poll_options or []
        return json.dumps(
            {
                "run_id": run.id,
                "channel_id": sched.poll_channel_id,
                "options": effective_options,
                "poll_duration_hours": sched.poll_duration_hours,
                "title": sched.name,
            }
        )

    async def _fire_poll(self, session, sched, now: datetime) -> None:  # type: ignore[no-untyped-def]
        run = await create_run(session, sched.id)
        payload = await self._build_poll_payload(run, sched)
        await self._valkey.publish(_CH_CREATE_POLL, payload)

        poll_ends_at = now + timedelta(hours=sched.poll_duration_hours)
        await update_run(
            session,
            run,
            status="poll_active",
            poll_starts_at=now,
            poll_ends_at=poll_ends_at,
        )

        next_poll = now + timedelta(days=sched.recurrence_days)
        await update_schedule(session, sched, next_poll_at=next_poll)
        logger.info(
            "CompetitionScheduleService: fired poll for schedule {} run {}",
            sched.id,
            run.id,
        )

    async def _fire_existing_run(self, session, sched, run, now: datetime) -> None:  # type: ignore[no-untyped-def]
        """Fire a pending_poll run that was created but never published (crash recovery)."""
        payload = await self._build_poll_payload(run, sched)
        await self._valkey.publish(_CH_CREATE_POLL, payload)
        poll_ends_at = now + timedelta(hours=sched.poll_duration_hours)
        await update_run(
            session,
            run,
            status="poll_active",
            poll_starts_at=now,
            poll_ends_at=poll_ends_at,
        )
        logger.info(
            "CompetitionScheduleService: recovered stuck pending_poll run {} for schedule {}",
            run.id,
            sched.id,
        )

    async def _republish_poll(self, session, run) -> None:  # type: ignore[no-untyped-def]
        from app.db.models.competition_schedule import CompetitionSchedule
        from sqlalchemy import select as sa_select

        sched = (
            await session.execute(
                sa_select(CompetitionSchedule).where(
                    CompetitionSchedule.id == run.schedule_id
                )
            )
        ).scalar_one_or_none()
        if not sched:
            return
        payload = await self._build_poll_payload(run, sched)
        await self._valkey.publish(_CH_CREATE_POLL, payload)
        logger.info(
            "CompetitionScheduleService: republished create_poll for unacknowledged run {}",
            run.id,
        )

    async def _request_poll_close(self, session, run) -> None:  # type: ignore[no-untyped-def]
        from app.db.models.competition_schedule import CompetitionSchedule
        from sqlalchemy import select as sa_select

        sched = (
            await session.execute(
                sa_select(CompetitionSchedule).where(
                    CompetitionSchedule.id == run.schedule_id
                )
            )
        ).scalar_one_or_none()
        if not sched:
            return
        effective_options = run.poll_options_override or sched.poll_options or []
        payload = json.dumps(
            {
                "run_id": run.id,
                "channel_id": run.discord_poll_channel_id,
                "message_id": run.discord_poll_message_id,
                "options": effective_options,
            }
        )
        await self._valkey.publish(_CH_CLOSE_POLL, payload)
        logger.info(
            "CompetitionScheduleService: requested poll close for overdue run {}",
            run.id,
        )

    async def _create_wom_competition(self, session, run) -> None:  # type: ignore[no-untyped-def]
        # Idempotency: if wom_competition_id already set, just fix status
        if run.wom_competition_id is not None:
            await update_run(session, run, status="competition_active")
            return

        from app.db.models.competition_schedule import CompetitionSchedule
        from sqlalchemy import select as sa_select

        sched = (
            await session.execute(
                sa_select(CompetitionSchedule).where(
                    CompetitionSchedule.id == run.schedule_id
                )
            )
        ).scalar_one_or_none()

        if not sched:
            await update_run(
                session, run, status="error", error_detail="schedule not found"
            )
            return

        now = _now()
        ends_at = now + timedelta(hours=sched.competition_duration_hours)
        metric = run.winning_metric or "overall"
        title = sched.title_template.replace(
            "{metric}", metric.replace("_", " ").title()
        )

        try:
            data = CreateCompetitionInput(
                title=title,
                metric=metric,
                starts_at=now,
                ends_at=ends_at,
                type="classic",
            )
            result = await create_competition(
                data,
                group_id=self._group_id,
                group_key=self._group_key,
                api_key=self._api_key,
                discord_contact=self._discord_contact,
            )
            wom_id = result.get("id")
            await update_run(
                session,
                run,
                status="competition_active",
                wom_competition_id=wom_id,
                competition_title=title,
                competition_starts_at=now,
                competition_ends_at=ends_at,
            )
            # Commit immediately - WOM comp exists; don't let an unrelated tick
            # failure in the same transaction roll this back and lose the link.
            await session.commit()
            logger.info(
                "CompetitionScheduleService: created WOM comp {} for run {}",
                wom_id,
                run.id,
            )
        except Exception as exc:
            logger.error(
                "CompetitionScheduleService: WOM comp creation failed for run {}: {}",
                run.id,
                exc,
            )
            await update_run(session, run, status="error", error_detail=str(exc))
            await session.commit()

    async def _announce_results(self, session, run) -> None:  # type: ignore[no-untyped-def]
        from app.db.models.competition_schedule import CompetitionSchedule
        from sqlalchemy import select as sa_select

        sched = (
            await session.execute(
                sa_select(CompetitionSchedule).where(
                    CompetitionSchedule.id == run.schedule_id
                )
            )
        ).scalar_one_or_none()

        top_results: list[dict] = []
        if run.wom_competition_id:
            try:
                async with WiseOldManHandler(
                    api_key=self._api_key,
                    discord_contact=self._discord_contact,
                    priority=WomPriority.NORMAL,
                ) as wom:
                    details = await wom.get_competition_details(run.wom_competition_id)
                participations = details.get("participations", [])
                participations.sort(
                    key=lambda p: (p.get("progress", {}) or {}).get("gained", 0),
                    reverse=True,
                )
                for rank, p in enumerate(participations[:10], 1):
                    top_results.append(
                        {
                            "rank": rank,
                            "rsn": p.get("player", {}).get("displayName", "?"),
                            "gained": (p.get("progress", {}) or {}).get("gained", 0),
                        }
                    )
            except Exception as exc:
                logger.warning(
                    "CompetitionScheduleService: could not fetch results for run {}: {}",
                    run.id,
                    exc,
                )

        payload = json.dumps(
            {
                "run_id": run.id,
                "results_channel_id": sched.results_channel_id if sched else None,
                "competition_title": run.competition_title or "Competition",
                "metric": run.winning_metric or "overall",
                "wom_competition_id": run.wom_competition_id,
                "top_results": top_results,
            }
        )
        await self._valkey.publish(_CH_ANNOUNCE, payload)
        await update_run(session, run, status="results_announced")
        logger.info("CompetitionScheduleService: announced results for run {}", run.id)

    # ── Subscriber loop ───────────────────────────────────────────────────

    async def _subscriber_loop(self) -> None:
        while True:
            client: Valkey = Valkey.from_url(_VALKEY_URI, socket_timeout=None)
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe(_CH_POLL_POSTED, _CH_POLL_RESULT)
                    logger.info(
                        "CompetitionScheduleService: subscribed to Valkey channels"
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            channel = raw["channel"]
                            if isinstance(channel, bytes):
                                channel = channel.decode()
                            if channel == _CH_POLL_POSTED:
                                await self._handle_poll_posted(data)
                            elif channel == _CH_POLL_RESULT:
                                await self._handle_poll_result(data)
                        except Exception as exc:
                            logger.warning(
                                "CompetitionScheduleService subscriber error: {}", exc
                            )
            except asyncio.CancelledError:
                logger.info("CompetitionScheduleService: subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "CompetitionScheduleService: subscriber lost connection ({}), reconnecting in 5s",
                    exc,
                )
                await client.aclose()
                await asyncio.sleep(5)

    async def _handle_poll_posted(self, data: dict) -> None:
        run_id = data.get("run_id")
        msg_id = data.get("discord_poll_message_id")
        channel_id = data.get("discord_poll_channel_id")
        if not run_id:
            return
        async with self._session_factory() as session:
            run = await get_run(session, run_id)
            if run:
                await update_run(
                    session,
                    run,
                    discord_poll_message_id=msg_id,
                    discord_poll_channel_id=channel_id,
                )
                await session.commit()

    async def _handle_poll_result(self, data: dict) -> None:
        run_id = data.get("run_id")
        if not run_id:
            return
        skipped = data.get("skipped", False)
        winning_metric = data.get("winning_metric")
        async with self._session_factory() as session:
            run = await get_run(session, run_id)
            if not run or run.status not in ("poll_active", "pending_poll"):
                return
            if skipped:
                await update_run(session, run, status="skipped")
                logger.info(
                    "CompetitionScheduleService: run {} skipped (no votes)", run_id
                )
            else:
                await update_run(
                    session,
                    run,
                    status="competition_pending",
                    winning_metric=winning_metric,
                )
                logger.info(
                    "CompetitionScheduleService: run {} poll resolved -> metric={}",
                    run_id,
                    winning_metric,
                )
            await session.commit()
