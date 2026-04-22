"""WiseOldMan API handler with smart in-memory competition cache."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

import httpx
from loguru import logger

from app.services.http.base import BaseRequestHandler


@dataclass
class _CachedComp:
    data: dict
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime | None  # None = infinite TTL (finished or upcoming)


def _comp_status(entry: _CachedComp) -> str:
    now = datetime.now(timezone.utc)
    if now < entry.starts_at:
        return "upcoming"
    if now <= entry.ends_at:
        return "ongoing"
    return "finished"


def _ttl_for(now: datetime, starts_at: datetime, ends_at: datetime) -> datetime | None:
    if now > ends_at:
        return None  # finished — cache forever
    if now >= starts_at:
        return now + timedelta(minutes=5)  # ongoing — 5 min TTL
    return None  # upcoming — no expiry (stale check uses starts_at)


def _parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class WiseOldManHandler(BaseRequestHandler):
    base_url = "https://api.wiseoldman.net/v2"
    default_timeout = 30.0

    # Shared across all instances (class-level competition cache)
    _comp_cache: ClassVar[dict[int, _CachedComp]] = {}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        discord_contact: str | None = None,
        group_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._group_key = group_key

        user_agent = (
            f"IronFoundry/1.0 (discord: @{discord_contact})"
            if discord_contact
            else "IronFoundry/1.0"
        )
        headers: dict[str, str] = {"User-Agent": user_agent}
        if api_key:
            headers["x-api-key"] = api_key
        if group_key:
            headers["x-wom-group-token"] = group_key

        # Instance attribute shadows ClassVar
        self.default_headers = headers  # type: ignore[assignment]

    async def _get_with_rate_limit(
        self,
        path: str,
        *,
        params: dict | None = None,
    ) -> httpx.Response:
        """GET with 429 retry and X-RateLimit-Remaining proactive sleep."""
        resp: httpx.Response | None = None
        for _ in range(2):
            resp = await self.get(path, params=params)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "10"))
                await asyncio.sleep(retry_after)
                continue
            if resp.is_success:
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "100"))
                if remaining <= 5:
                    reset_in = float(resp.headers.get("X-RateLimit-Reset", "2"))
                    await asyncio.sleep(max(reset_in, 0.5))
            return resp
        return resp  # type: ignore[return-value]


    async def get_group(self, group_id: str | int) -> dict:
        resp = await self.get(f"/groups/{group_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_group_hiscores(
        self,
        group_id: str | int,
        metric: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        resp = await self._get_with_rate_limit(
            f"/groups/{group_id}/hiscores",
            params={"metric": metric, "limit": limit, "offset": offset},
        )
        if not resp.is_success:
            return []
        return resp.json()

    async def get_group_name_changes(
        self, group_id: str | int, *, limit: int = 50
    ) -> list[dict]:
        resp = await self.get(
            f"/groups/{group_id}/name-changes",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_group_competitions(
        self,
        group_id: str | int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        resp = await self._get_with_rate_limit(
            f"/groups/{group_id}/competitions",
            params={"limit": limit, "offset": offset},
        )
        if not resp.is_success:
            logger.warning(
                "wom: GET /groups/{}/competitions offset={} returned HTTP {}",
                group_id, offset, resp.status_code,
            )
            return []
        return resp.json()

    async def get_competition_details(
        self, comp_id: int, *, metric: str | None = None
    ) -> dict:
        params: dict | None = {"metric": metric} if metric else None
        resp = await self.get(f"/competitions/{comp_id}", params=params)
        resp.raise_for_status()
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
        self, group_id: str | int, metric: str, top_n: int = 10
    ) -> list[dict] | None:
        """Fetch top top_n players for one WOM metric, retrying once on 429."""
        for _ in range(2):
            try:
                resp = await self.get(
                    f"/groups/{group_id}/hiscores",
                    params={"metric": metric, "limit": top_n, "offset": 0},
                )
            except Exception:
                return None

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "10"))
                await asyncio.sleep(retry_after)
                continue

            if not resp.is_success:
                return None

            remaining = int(resp.headers.get("X-RateLimit-Remaining", "100"))
            if remaining <= 5:
                reset_in = float(resp.headers.get("X-RateLimit-Reset", "2"))
                await asyncio.sleep(max(reset_in, 0.5))

            return [
                {"player_name": e["player"]["displayName"], "kills": e["data"]["kills"]}
                for e in resp.json()
                if (e.get("data", {}).get("kills") or 0) > 0
            ]

        return None

    # ------------------------------------------------------------------
    # Competition cache
    # ------------------------------------------------------------------

    async def get_cached_competition(
        self,
        comp_id: int,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        *,
        metric: str | None = None,
    ) -> dict:
        """Return competition details from cache, fetching/refreshing as needed."""
        entry = self._comp_cache.get(comp_id)
        now = datetime.now(timezone.utc)

        stale = True
        if entry is not None:
            stale = (
                (entry.expires_at is not None and now >= entry.expires_at)
                or (now >= entry.starts_at and _comp_status(entry) == "upcoming")
            )

        if stale:
            data = await self.get_competition_details(comp_id, metric=metric)
            if starts_at is None:
                starts_at = _parse_dt(data["startsAt"])
            if ends_at is None:
                ends_at = _parse_dt(data["endsAt"])
            self._comp_cache[comp_id] = _CachedComp(
                data=data,
                starts_at=starts_at,
                ends_at=ends_at,
                expires_at=_ttl_for(now, starts_at, ends_at),
            )

        return self._comp_cache[comp_id].data

    async def get_all_group_competitions(
        self,
        group_id: str | int,
        *,
        max_finished: int = 30,
    ) -> list[dict]:
        """Fetch recent group competitions with derived status + urls.

        Paginates WOM in pages of 50 (WOM's actual page size) and stops once
        ``max_finished`` finished competitions have been collected, so we never
        fetch hundreds of historical pages for active groups.
        """
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
                logger.debug("wom: competitions page empty at offset={} — done", offset)
                break
            all_comps.extend(page)
            for comp in page:
                ends_at = _parse_dt(comp["endsAt"])
                if now > ends_at:
                    finished_seen += 1
            logger.debug(
                "wom: got {} competitions (total: {}, finished so far: {})",
                len(page), len(all_comps), finished_seen,
            )
            if len(page) < limit:
                break
            if finished_seen >= max_finished:
                logger.debug(
                    "wom: hit max_finished={} threshold — stopping pagination", max_finished
                )
                break
            offset += len(page)

        logger.info("wom: fetched {} competitions total for group={}", len(all_comps), group_id)

        now = datetime.now(timezone.utc)
        result: list[dict] = []
        for comp in all_comps:
            starts_at = _parse_dt(comp["startsAt"])
            ends_at = _parse_dt(comp["endsAt"])
            if now < starts_at:
                status = "upcoming"
            elif now <= ends_at:
                status = "ongoing"
            else:
                status = "finished"
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
