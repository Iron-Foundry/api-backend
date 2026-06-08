"""WOM competition-related API methods mixin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from app.services.http.wom_queue import get_wom_queue
from .wom_cache import _CachedComp, _comp_status, _ttl_for, parse_dt


class WomCompetitionMixin:
    _comp_cache: ClassVar[dict[int, _CachedComp]] = {}

    async def create_competition(self, payload: dict) -> dict:
        resp = await self._write_with_rate_limit("post", "/competitions", json=payload)  # type: ignore[attr-defined]
        resp.raise_for_status()
        return resp.json()

    async def edit_competition(self, comp_id: int, payload: dict) -> dict:
        resp = await self._write_with_rate_limit("put", f"/competitions/{comp_id}", json=payload)  # type: ignore[attr-defined]
        resp.raise_for_status()
        return resp.json()

    async def delete_competition(self, comp_id: int, payload: dict) -> None:
        resp = await self._write_with_rate_limit("delete", f"/competitions/{comp_id}", json=payload)  # type: ignore[attr-defined]
        resp.raise_for_status()

    async def get_competition_top5_progress(self, comp_id: int, metric: str) -> list[dict]:
        resp = await self._get_with_rate_limit(f"/competitions/{comp_id}/top5-progress", params={"metric": metric})  # type: ignore[attr-defined]
        return resp.json() if resp.is_success else []

    async def get_competition_details(self, comp_id: int, *, metric: str | None = None) -> dict:
        params: dict | None = {"metric": metric} if metric else None
        queue = get_wom_queue()
        resp = await queue.submit(
            lambda cid=comp_id, p=params: self.get(f"/competitions/{cid}", params=p),  # type: ignore[attr-defined]
            self._priority,  # type: ignore[attr-defined]
        )
        resp.raise_for_status()
        return resp.json()

    async def get_competition_details_at(self, comp_id: int, *, metric: str, date: datetime) -> dict:
        """Fetch competition standings as of a specific UTC datetime."""
        params = {"metric": metric, "date": date.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        queue = get_wom_queue()
        resp = await queue.submit(
            lambda cid=comp_id, p=params: self.get(f"/competitions/{cid}", params=p),  # type: ignore[attr-defined]
            self._priority,  # type: ignore[attr-defined]
        )
        resp.raise_for_status()
        return resp.json()

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

        stale = entry is None or (entry.expires_at is not None and now >= entry.expires_at) or (
            now >= entry.starts_at and _comp_status(entry) == "upcoming"
        )

        if stale:
            data = await self.get_competition_details(comp_id, metric=metric)
            if starts_at is None:
                starts_at = parse_dt(data["startsAt"])
            if ends_at is None:
                ends_at = parse_dt(data["endsAt"])
            self._comp_cache[comp_id] = _CachedComp(
                data=data, starts_at=starts_at, ends_at=ends_at, expires_at=_ttl_for(now, starts_at, ends_at)
            )

        return self._comp_cache[comp_id].data
