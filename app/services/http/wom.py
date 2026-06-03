"""WiseOldMan API handler with smart in-memory competition cache."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

import httpx
from loguru import logger

from app.services.http.base import BaseRequestHandler

# Shared rate-limit bucket - one bucket for all WiseOldManHandler instances.
# WOM uses express-rate-limit with standardHeaders (IETF draft):
#   RateLimit-Remaining: <n>
#   RateLimit-Reset: <seconds until window ends>  (delta, not epoch)
_rl_remaining: int = 60
_rl_reset_at: float = 0.0  # time.monotonic() deadline


def _rl_update(headers: httpx.Headers) -> None:
    global _rl_remaining, _rl_reset_at
    raw_remaining = headers.get("ratelimit-remaining")
    raw_reset = headers.get("ratelimit-reset")
    if raw_remaining is not None:
        try:
            _rl_remaining = int(raw_remaining)
        except ValueError:
            pass
    if raw_reset is not None:
        try:
            _rl_reset_at = time.monotonic() + float(raw_reset)
        except ValueError:
            pass


async def _rl_proactive_sleep() -> None:
    if _rl_remaining <= 1:
        wait = _rl_reset_at - time.monotonic()
        if wait > 0:
            logger.debug("wom: rate limit bucket exhausted, sleeping {:.1f}s", wait)
            await asyncio.sleep(wait + 0.25)


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
        return None  # finished - cache forever
    if now >= starts_at:
        return now + timedelta(minutes=5)  # ongoing - 5 min TTL
    return None  # upcoming - no expiry (stale check uses starts_at)


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
        """GET with shared-bucket proactive sleep and 429 retry."""
        resp: httpx.Response | None = None
        for attempt in range(3):
            await _rl_proactive_sleep()
            resp = await self.get(path, params=params)
            _rl_update(resp.headers)
            if resp.status_code != 429:
                return resp
            retry_after = float(resp.headers.get("retry-after", "5"))
            logger.warning(
                "wom: 429 on {} (attempt {}) - sleeping {:.1f}s",
                path,
                attempt + 1,
                retry_after,
            )
            await asyncio.sleep(retry_after)
        return resp  # type: ignore[return-value]

    async def _write_with_rate_limit(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
    ) -> httpx.Response:
        """POST/PUT/DELETE with shared-bucket proactive sleep and 429 retry."""
        resp: httpx.Response | None = None
        for attempt in range(3):
            await _rl_proactive_sleep()
            if method == "post":
                resp = await self.post(path, json=json)
            elif method == "put":
                resp = await self.put(path, json=json)
            else:
                resp = await self.delete(path, json=json)
            _rl_update(resp.headers)
            if resp.status_code != 429:
                return resp
            retry_after = float(resp.headers.get("retry-after", "5"))
            logger.warning(
                "wom: 429 on {} {} (attempt {}) - sleeping {:.1f}s",
                method.upper(),
                path,
                attempt + 1,
                retry_after,
            )
            await asyncio.sleep(retry_after)
        return resp  # type: ignore[return-value]

    async def create_competition(self, payload: dict) -> dict:
        resp = await self._write_with_rate_limit("post", "/competitions", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def edit_competition(self, comp_id: int, payload: dict) -> dict:
        resp = await self._write_with_rate_limit(
            "put", f"/competitions/{comp_id}", json=payload
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_competition(self, comp_id: int, payload: dict) -> None:
        resp = await self._write_with_rate_limit(
            "delete", f"/competitions/{comp_id}", json=payload
        )
        resp.raise_for_status()

    async def get_competition_top5_progress(
        self, comp_id: int, metric: str
    ) -> list[dict]:
        resp = await self._get_with_rate_limit(
            f"/competitions/{comp_id}/top5-progress",
            params={"metric": metric},
        )
        if not resp.is_success:
            return []
        return resp.json()

    async def get_group(self, group_id: str | int) -> dict:
        resp = await self._get_with_rate_limit(f"/groups/{group_id}")
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

    async def get_player_details(self, username: str) -> dict:
        resp = await self._get_with_rate_limit(f"/players/{username}")
        return resp.json() if resp.is_success else {}

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
                group_id,
                offset,
                resp.status_code,
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

    async def get_competition_details_at(
        self, comp_id: int, *, metric: str, date: datetime
    ) -> dict:
        """Fetch competition participant standings as of a specific UTC datetime.

        WOM reconstructs standings from the closest player snapshots it has on
        record at or before ``date``.
        """
        params = {
            "metric": metric,
            "date": date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
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
        self, group_id: str | int, metric: str, top_n: int = 600
    ) -> list[dict] | None:
        """Fetch up to top_n players for one WOM metric, paginating as needed."""
        page_size = 50
        offset = 0
        results: list[dict] = []
        try:
            while len(results) < top_n:
                fetch = min(page_size, top_n - len(results))
                resp = await self._get_with_rate_limit(
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
            stale = (entry.expires_at is not None and now >= entry.expires_at) or (
                now >= entry.starts_at and _comp_status(entry) == "upcoming"
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
                logger.debug("wom: competitions page empty at offset={} - done", offset)
                break
            all_comps.extend(page)
            for comp in page:
                ends_at = _parse_dt(comp["endsAt"])
                if now > ends_at:
                    finished_seen += 1
            logger.debug(
                "wom: got {} competitions (total: {}, finished so far: {})",
                len(page),
                len(all_comps),
                finished_seen,
            )
            if len(page) < limit:
                break
            if finished_seen >= max_finished:
                logger.debug(
                    "wom: hit max_finished={} threshold - stopping pagination",
                    max_finished,
                )
                break
            offset += len(page)

        logger.info(
            "wom: fetched {} competitions total for group={}", len(all_comps), group_id
        )

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
