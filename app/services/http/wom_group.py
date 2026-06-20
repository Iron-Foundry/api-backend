"""WOM group-related API methods mixin."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from app.services.http.wom_queue import get_wom_queue
from .wom_cache import parse_dt


class WomGroupMixin:
    async def get_group(self, group_id: str | int) -> dict:
        resp = await self._get_with_rate_limit(f"/groups/{group_id}")  # type: ignore[attr-defined]
        resp.raise_for_status()
        return resp.json()

    async def get_group_hiscores(
        self, group_id: str | int, metric: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        resp = await self._get_with_rate_limit(  # type: ignore[attr-defined]
            f"/groups/{group_id}/hiscores",
            params={"metric": metric, "limit": limit, "offset": offset},
        )
        return resp.json() if resp.is_success else []

    async def get_group_name_changes(
        self, group_id: str | int, *, limit: int = 50
    ) -> list[dict]:
        queue = get_wom_queue()
        resp = await queue.submit(
            lambda gid=group_id, lim=limit: self.get(
                f"/groups/{gid}/name-changes", params={"limit": lim}
            ),  # type: ignore[attr-defined]
            self._priority,  # type: ignore[attr-defined]
        )
        resp.raise_for_status()
        return resp.json()

    async def get_group_competitions(
        self, group_id: str | int, *, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        resp = await self._get_with_rate_limit(  # type: ignore[attr-defined]
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

    async def fetch_metric_total(self, group_id: str | int, metric: str) -> int:
        """Sum kills across all group members for a single WOM metric."""
        total = 0
        limit = 50
        offset = 0
        while True:
            page = await self.get_group_hiscores(
                group_id, metric, limit=limit, offset=offset
            )
            if not page:
                break
            for entry in page:
                total += entry.get("data", {}).get("kills", 0) or 0
            if len(page) < limit:
                break
            offset += limit
        return total

    async def fetch_kc_metric(
        self, group_id: str | int, metric: str, top_n: int = 600
    ) -> list[dict] | None:
        """Fetch up to top_n players for one WOM metric, paginating as needed."""
        page_size = 50
        offset = 0
        results: list[dict] = []
        try:
            while len(results) < top_n:
                fetch = min(page_size, top_n - len(results))
                resp = await self._get_with_rate_limit(  # type: ignore[attr-defined]
                    f"/groups/{group_id}/hiscores",
                    params={"metric": metric, "limit": fetch, "offset": offset},
                )
                if not resp.is_success:
                    break
                page = resp.json()
                if not page:
                    break
                for e in page:
                    if (e.get("data", {}).get("kills") or 0) > 0:
                        results.append(
                            {
                                "player_name": e["player"]["displayName"],
                                "kills": e["data"]["kills"],
                            }
                        )
                if len(page) < fetch:
                    break
                offset += fetch
        except Exception:
            return None
        return results or None

    async def get_all_group_competitions(
        self, group_id: str | int, *, max_finished: int = 30
    ) -> list[dict]:
        """Fetch recent group competitions with derived status. Stops after max_finished finished ones."""
        all_comps: list[dict] = []
        limit = 50
        offset = 0
        finished_seen = 0
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
        result: list[dict] = []
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
