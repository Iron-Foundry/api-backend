"""WOM group-related API methods mixin."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from app.services.http.wom_queue import get_wom_queue

from .wom_base import WomHandlerBase
from .wom_cache import parse_dt


class WomGroupMixin(WomHandlerBase):
    async def get_group(self, group_id: str | int) -> dict[str, Any]:
        resp = await self._get_with_rate_limit(f"/groups/{group_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_group_name_changes(
        self, group_id: str | int, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        queue = get_wom_queue()
        resp = await queue.submit(
            lambda gid=group_id, lim=limit: self.get(
                f"/groups/{gid}/name-changes", params={"limit": lim}
            ),
            self._priority,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_group_competitions(
        self, group_id: str | int, *, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        resp = await self._get_with_rate_limit(
            f"/groups/{group_id}/competitions",
            params={"limit": limit, "offset": offset},
        )
        if not resp.is_success:
            logger.warning(
                "wom: GET /groups/{}/competitions offset={} returned HTTP {}",
                group_id,
                offset,
                resp.status_code,
            )
            return []
        return resp.json()

    async def get_group_bulk_hiscores(
        self, group_id: str | int
    ) -> list[dict[str, Any]]:
        resp = await self._get_with_rate_limit(f"/groups/{group_id}/bulk-hiscores")
        if not resp.is_success:
            logger.warning(
                "wom: GET /groups/{}/bulk-hiscores returned HTTP {}",
                group_id,
                resp.status_code,
            )
            return []
        return resp.json()

    async def get_group_bulk_gains(
        self,
        group_id: str | int,
        *,
        period: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if period:
            params["period"] = period
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        resp = await self._get_with_rate_limit(
            f"/groups/{group_id}/bulk-gained", params=params
        )
        if not resp.is_success:
            logger.warning(
                "wom: GET /groups/{}/bulk-gained returned HTTP {}",
                group_id,
                resp.status_code,
            )
            return []
        return resp.json()

    async def get_all_group_competitions(
        self, group_id: str | int, *, max_finished: int = 30
    ) -> list[dict[str, Any]]:
        """Fetch recent group competitions with derived status. Stops after max_finished finished ones."""
        all_comps: list[dict[str, Any]] = []
        limit = 50
        offset = 0
        finished_seen = 0
        now = datetime.now(UTC)
        logger.info("wom: fetching group competitions (group={})", group_id)
        while True:
            logger.debug("wom: GET /groups/{}/competitions offset={}", group_id, offset)
            page = await self.get_group_competitions(
                group_id, limit=limit, offset=offset
            )
            if not page:
                break
            all_comps.extend(page)
            for comp in page:
                if now > parse_dt(comp["endsAt"]):
                    finished_seen += 1
            logger.debug(
                "wom: got {} competitions (total: {}, finished: {})",
                len(page),
                len(all_comps),
                finished_seen,
            )
            if len(page) < limit or finished_seen >= max_finished:
                break
            offset += len(page)

        logger.info(
            "wom: fetched {} competitions total for group={}", len(all_comps), group_id
        )
        now = datetime.now(UTC)
        result: list[dict[str, Any]] = []
        for comp in all_comps:
            starts_at = parse_dt(comp["startsAt"])
            ends_at = parse_dt(comp["endsAt"])
            status = (
                "upcoming"
                if now < starts_at
                else ("ongoing" if now <= ends_at else "finished")
            )
            comp_id = comp["id"]
            metric = comp.get("metric", "")
            result.append(
                {
                    **comp,
                    "status": status,
                    "competition_url": f"https://wiseoldman.net/competitions/{comp_id}",
                    "metric_url": f"https://wiseoldman.net/competitions/{comp_id}?metric={metric}",
                }
            )
        return result
